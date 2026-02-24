import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import uuid
import os

load_dotenv() # Explicitly load .env file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secret_key_for_session")

# File Upload Config
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    
socketio = SocketIO(app, cors_allowed_origins="*")

# Google OAuth Setup
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID', '').strip('"').strip("'"),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', '').strip('"').strip("'"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# In-memory storage for meetings (Active rooms)
active_meetings = set()

@app.route('/', methods=['GET', 'POST'])
def index():
    user = session.get('user')
    return render_template('index.html', user=user)

@app.route('/login/google')
def login_google():
    # Use 127.0.0.1 specifically to match the common local dev redirect URI
    redirect_uri = url_for('callback', _external=True)
    
    # Debug log to help the user verify their Google Console setup
    print(f"DEBUG: Redirecting to Google with URI: {redirect_uri}")
    
    return google.authorize_redirect(redirect_uri)

@app.route('/callback')
def callback():
    token = google.authorize_access_token()
    # In OpenID Connect, user info is often available in the 'userinfo' key of the token result
    user_info = token.get('userinfo')
    
    if not user_info:
        # Fallback if userinfo is not in token
        user_info = google.get('https://openidconnect.googleapis.com/v1/userinfo').json()
    
    # Store Google profile info in session
    session['user'] = user_info.get('name')
    session['email'] = user_info.get('email')
    session['picture'] = user_info.get('picture')
    
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/upload_file/<room_id>', methods=['POST'])
def upload_file(room_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        # Append UUID to filename to avoid collisions
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        
        # Notify room via socket
        socketio.emit('file-shared', {
            'filename': filename,
            'url': url_for('download_file', filename=unique_filename),
            'sender': session.get('user', 'Anonymous')
        }, room=room_id)
        
        return jsonify({'success': True, 'filename': filename})

@app.route('/download_file/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/create_meeting', methods=['POST'])
def create_meeting_flow():
    password = request.form.get('password')
    if password == "1@#1#23":
        room_id = str(uuid.uuid4())[:8]
        active_meetings.add(room_id)
        session['role'] = 'teacher' # Creator becomes teacher
        return redirect(f'/meeting/{room_id}')
    else:
        return render_template('index.html', user=session['user'], error="Incorrect password to create meeting")

@app.route('/join_meeting', methods=['POST'])
def join_meeting_flow():
    room_id = request.form.get('room_id')
    if room_id in active_meetings:
        session['role'] = 'student' # Joiner is student
        return redirect(f'/meeting/{room_id}')
    else:
        return render_template('index.html', user=session['user'], error="Meeting ID not found or invalid")

@app.route('/end_meeting/<room_id>', methods=['POST'])
def end_meeting(room_id):
    if room_id in active_meetings:
        active_meetings.remove(room_id)
        socketio.emit('meeting-ended', room=room_id)
    return jsonify({'success': True})

@app.route('/meeting/<room_id>')
def meeting(room_id):
    if room_id not in active_meetings:
         return redirect(url_for('index', error="Meeting has ended or is invalid."))

    return render_template('meeting.html', 
                           room=room_id, 
                           user=session.get('user', 'Guest'), 
                           role=session.get('role', 'student'),
                           picture=session.get('picture', ''))

# SocketIO Events
connected_users = {}

@socketio.on('join')
def handle_join(data):
    room = data['room']
    join_room(room)
    
    # Store user info
    connected_users[request.sid] = {
        'room': room,
        'username': session.get('user', 'Anonymous'),
        'picture': session.get('picture', '')
    }

    # Tell the joiner about existing users
    existing_users = []
    for sid, info in connected_users.items():
        if info['room'] == room and sid != request.sid:
            existing_users.append({
                'sid': sid,
                'username': info['username'],
                'picture': info['picture']
            })
    
    emit('all-users', existing_users)
    
    emit('new-user', {
        'sid': request.sid,
        'username': session.get('user', 'Anonymous'),
        'picture': session.get('picture', '')
    }, room=room, include_self=False)

@socketio.on('signal')
def handle_signal(data):
    emit('signal', {
        'signal': data['signal'],
        'from': request.sid
    }, room=data['to'])

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in connected_users:
        user_info = connected_users[request.sid]
        room = user_info['room']
        username = user_info['username']
        
        connected_users.pop(request.sid, None)
        
        emit('user-left', {
            'sid': request.sid,
            'username': username
        }, room=room)

@socketio.on('leave-room')
def handle_leave(data):
    room = data['room']
    leave_room(room)
    
    connected_users.pop(request.sid, None)
        
    emit('user-left', {
        'sid': request.sid,
        'username': session.get('user', 'Anonymous')
    }, room=room, include_self=False)

@socketio.on('raise-hand')
def handle_raise_hand(data):
    emit('raise-hand', {
        'sid': request.sid,
        'username': session.get('user', 'Anonymous')
    }, room=data['room'], include_self=False)

@socketio.on('video-filter')
def handle_filter(data):
    emit('video-filter', {
        'sid': request.sid,
        'filter': data['filter']
    }, room=data['room'], include_self=False)

@socketio.on('chat')
def handle_chat(data):
    username = session.get('user', 'Anonymous')
    picture = session.get('picture', '')
    emit('chat', {
        'msg': data['msg'],
        'username': username,
        'picture': picture,
        'sid': request.sid
    }, room=data['room'], include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
