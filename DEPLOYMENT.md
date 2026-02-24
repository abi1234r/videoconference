# Deploying to Render.com

This guide explains how to deploy the Video Conference App to Render.com.

## Prerequisites
- A GitHub account
- A Render.com account

## Steps

### 1. Push your code to GitHub
- Create a new repository on GitHub.
- Push your project code to this new repository.

### 2. Create a PostgreSQL Database
To ensure user data isn't lost when the app restarts, we need a standard database.
- Go to your Render Dashboard.
- Click **New +** -> **PostgreSQL**.
- **Name:** `video-app-db` (or similar).
- **User:** `user` (or leave default).
- **Region:** Same as your web service (e.g., Singapore, Oregon).
- **Instance Type:** Free.
- Click **Create Database**.
- Wait for it to be created.
- **Copy the "Internal Database URL"**. You will need this shortly.

### 3. Create a Web Service
- Go back to Render Dashboard.
- Click **New +** -> **Web Service**.
- Connect your GitHub repository.
- **Name:** `my-video-app`.
- **Runtime:** `Python 3`.
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn -k eventlet -w 1 app:app`
- **Instance Type:** Free.

### 4. Configure Environment Variables
This is the critical step to connect your database.
- Scroll down to **Environment Variables**.
- Click **Add Environment Variable**.
- **Key:** `DATABASE_URL`
- **Value:** Paste the **Internal Database URL** you copied from the database setup (starts with `postgres://`).
- Click **Create Web Service**.

### 5. Initialize the Database
Once the app is running, the database tables will be created automatically because `database.init_db()` is called in `app.py`.

However, to add the initial specific users (teacher/admin), you can run the seed script remotely or just use the Admin Dashboard later once you create a user manually.
**Recommendation:** Use the app's Admin Dashboard (if you have an admin user).
*Since the remote DB is empty, you don't have an admin user yet.*
You can execute the seed script via Render's "Shell" tab:
1. Go to your Web Service in Render.
2. Click on the **Shell** tab on the left.
3. Run: `python seed_db.py`
4. This will create the default users:
   - `teacher` / `1234`
   - `student` / `1234`
   - `admin` / `admin123`

## Done!
Your application is now live with a persistent database.
