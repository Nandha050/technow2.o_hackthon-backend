import sqlite3
import json
import requests
import time
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from pytube import Search

app = Flask(__name__)
CORS(app)

DB_FILE = os.path.join(os.getcwd(), 'cache.db')

# Initialize database
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                query TEXT,
                category TEXT,
                results TEXT,
                timestamp INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE,
                link TEXT
            )
        ''')
        conn.commit()

init_db()

# Fetch data from API
def fetch_data(url, headers=None):
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"API Error: {e}")
        return {}
def fetch_google_thumbnail(query):
    API_KEY = "AIzaSyAhcC9YkEX5-e5NfvxT0jVyOp1dAvhagVI"
    SEARCH_ENGINE_ID = "125482c733a3b4f2b"
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&cx={SEARCH_ENGINE_ID}&searchType=image&num=1&key={API_KEY}"
    
    data = fetch_data(url)
    if "items" in data:
        return data["items"][0]["link"]
    return "https://via.placeholder.com/150"  # Default placeholder

# Fetch Coursera courses
def fetch_coursera_courses(query):
    url = f"https://www.coursera.org/api/courses.v1?q=search&query={query}&includes=photoUrl"
    data = fetch_data(url)
    courses = [{"title": "Intro to AI", "link": "https://coursera.org/ai"}]  # Example
    for course in courses:
        course["thumbnail"] = fetch_google_thumbnail(course["title"])
    return [
        {
            "title": course["name"],
            "link": f"https://www.coursera.org/learn/{course['slug']}",
            "thumbnail": course.get("photoUrl", "default-course-thumbnail.jpg")  # Auto-fetch image
        } 
        for course in data.get("elements", [])
    ]

# Fetch Dev.to blogs
def fetch_devto_blogs(query):
    url = f"https://dev.to/api/articles?tag={query}"
    data = fetch_data(url)

    return [
        {
            "title": blog["title"],
            "link": blog["url"],
            "thumbnail": blog.get("cover_image", "default-blog-thumbnail.jpg")  # Use cover image if available
        }
        for blog in data
    ]


# YouTube Search API (Ensure valid API key)
YOUTUBE_API_KEY = "AIzaSyCGLMeMzNoBmI1QnInrPx_Vrt9GqMm47y0"

def search_youtube(query):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&type=video&maxResults=5&key={YOUTUBE_API_KEY}"
    data = fetch_data(url)

    return [
        {
            "title": item["snippet"]["title"],
            "link": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]  # Fetch YouTube thumbnail
        }
        for item in data.get("items", [])
    ]


# Fetch jobs
def fetch_jobs(query):
    return [
        {
            "title": f"{query} Jobs on LinkedIn",
            "link": f"https://www.linkedin.com/jobs/search/?keywords={query}",
            "thumbnail": "default-job-thumbnail.jpg"  # Default image for jobs
        }
    ]


# Fetch internships
def fetch_internships(query):
    return [
        {
            "title": f"Internships in {query} (Internshala)",
            "link": f"https://internshala.com/internships/{query}-internship",
            "thumbnail": "default-internship-thumbnail.jpg"  # Default image for internships
        }
    ]

# Cache handling
def get_cached_results(query, category):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT results FROM cache WHERE query=? AND category=?", (query, category))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None

def cache_results(query, category, results):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO cache (query, category, results, timestamp) VALUES (?, ?, ?, ?)",
                       (query, category, json.dumps(results), int(time.time())))
        conn.commit()

# Main search function
def search_resources(query, category=None):
    cached_results = get_cached_results(query, category)
    if cached_results:
        return cached_results

    results = []
    
    if category:
        if category == "Course":
            results = fetch_coursera_courses(query)
        elif category == "Blog":
            results = fetch_devto_blogs(query)
        elif category == "YouTube":
            results = search_youtube(query)
        elif category == "Job":
            results = fetch_jobs(query)
        elif category == "Internship":
            results = fetch_internships(query)
    else:
        # Fetch all categories when no category is selected
        results.extend(fetch_coursera_courses(query))
        results.extend(fetch_devto_blogs(query))
        results.extend(search_youtube(query))
        results.extend(fetch_jobs(query))
        results.extend(fetch_internships(query))

    cache_results(query, category, results)
    return results

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get("query", "").strip()
    category = request.args.get("category")
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400
    return jsonify({"category": category, "query": query, "results": search_resources(query, category)})

@app.route('/save-course', methods=['POST'])
def save_course():
    data = request.json
    title, link = data.get("title"), data.get("link")
    if not title or not link:
        return jsonify({"error": "Title and link are required"}), 400
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO saved_courses (title, link) VALUES (?, ?)", (title, link))
        conn.commit()
    return jsonify({"message": "Course saved successfully!"})

@app.route('/saved-courses', methods=['GET'])
def get_saved_courses():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, link FROM saved_courses")
        return jsonify({"savedCourses": [{"title": row[0], "link": row[1]} for row in cursor.fetchall()]})

@app.route('/remove-course', methods=['DELETE'])
def remove_course():
    title = request.json.get("title")
    if not title:
        return jsonify({"error": "Title is required"}), 400
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_courses WHERE title=?", (title,))
        conn.commit()
    return jsonify({"message": "Course removed successfully!"})

if __name__ == "__main__":
    app.run(debug=True)
