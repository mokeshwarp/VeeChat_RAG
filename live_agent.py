from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request
from threading import Lock
import uuid
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Create logs directory if it doesn't exist
LOGS_DIR = 'logs'
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# Track available agents and active sessions
available_agents = {
    "erp": [],  # List of available ERP agent socket IDs
    "sales": []  # List of available Sales agent socket IDs
}

active_sessions = {}  # session_id -> {agent_sid, client_sid, room_id, support_type, messages, start_time}
user_sessions = {}    # socket_id -> session_id
lock = Lock()

def save_session_log(session_id, session_data):
    """Save session conversation to a log file"""
    try:
        log_filename = f"{session_id}.txt"
        log_filepath = os.path.join(LOGS_DIR, log_filename)
        
        with open(log_filepath, 'w', encoding='utf-8') as f:
            # Write session header
            f.write("=" * 50 + "\n")
            f.write(f"SESSION LOG\n")
            f.write("=" * 50 + "\n")
            f.write(f"Session ID: {session_id}\n")
            f.write(f"Support Type: {session_data['support_type'].upper()}\n")
            f.write(f"Client: {session_data['client_username']}\n")
            f.write(f"Agent: {session_data['agent_username']}\n")
            f.write(f"Started: {session_data['start_time']}\n")
            f.write(f"Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            
            # Write conversation messages
            f.write("CONVERSATION:\n")
            f.write("-" * 30 + "\n")
            
            if session_data['messages']:
                for message in session_data['messages']:
                    f.write(f"[{message['timestamp']}] {message['content']}\n")
            else:
                f.write("No messages exchanged in this session.\n")
            
            f.write("\n" + "=" * 50 + "\n")
            f.write("END OF SESSION LOG\n")
            f.write("=" * 50 + "\n")
        
        print(f"Session log saved: {log_filepath}")
        
    except Exception as e:
        print(f"Error saving session log for {session_id}: {str(e)}")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/client/erp')
def client_erp():
    return render_template('client1.html', support_type="ERP", room="erp_room")

@app.route('/client/sales')
def client_sales():
    return render_template('client1.html', support_type="Sales", room="sales_room")

@app.route('/agent/erp')
def erp_agent():
    return render_template('agent1.html', agent_type="ERP", room="erp_room")

@app.route('/agent/sales')
def sales_agent():
    return render_template('agent1.html', agent_type="Sales", room="sales_room")

@socketio.on('join')
def handle_join(data):
    
    username = data['username']
    support_type = data.get('room', '').replace('_room', '')  # Extract support type from room
    
    with lock:
        if "Agent" in username:
            # Agent joining - add to available agents
            if support_type in available_agents:
                available_agents[support_type].append(request.sid)
                emit('status', {'msg': f'You are now available for {support_type.upper()} support'})
                print(f"Agent {username} added to {support_type} pool. Available agents: {len(available_agents[support_type])}")
        else:
            # Client joining - try to match with available agent
            if support_type in available_agents and available_agents[support_type]:
                # Get an available agent
                agent_sid = available_agents[support_type].pop(0)
                
                # Create a new session
                session_id = str(uuid.uuid4())
                room_id = f"{support_type}_session_{session_id[:8]}"
                
                # Store session information with message logging
                active_sessions[session_id] = {
                    'agent_sid': agent_sid,
                    'client_sid': request.sid,
                    'room_id': room_id,
                    'support_type': support_type,
                    'agent_username': f"Agent-{support_type.upper()}",
                    'client_username': username,
                    'messages': [],  # Store all messages for logging
                    'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                user_sessions[request.sid] = session_id
                user_sessions[agent_sid] = session_id
                
                # Join both agent and client to the session room
                join_room(room_id)
                socketio.server.enter_room(agent_sid, room_id)
                
                # Notify both parties
                emit('session_started', {
                    'room': room_id,
                    'msg': f'Connected to {support_type.upper()} support agent'
                })
                
                socketio.emit('session_started', {
                    'room': room_id,
                    'msg': f'New client connected: {username}'
                }, room=agent_sid)
                
                # Send welcome message to the session room and log it
                welcome_msg = f'Session started. Agent and {username} are now connected.'
                socketio.emit('message', {
                    'msg': welcome_msg,
                    'system': True
                }, room=room_id)
                
                # Log the welcome message
                active_sessions[session_id]['messages'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'content': f"SYSTEM: {welcome_msg}"
                })
                
                print(f"Session {session_id[:8]} created: {username} <-> Agent-{support_type.upper()}")
                
            else:
                # No available agents
                emit('agent_unavailable', {
                    'msg': f'No {support_type.upper()} agents are currently available. Please wait...'
                })
                print(f"No available {support_type} agents for client {username}")

@socketio.on('disconnect')
def handle_disconnect():
    from flask import request
    
    with lock:
        if request.sid in user_sessions:
            session_id = user_sessions[request.sid]
            
            if session_id in active_sessions:
                session = active_sessions[session_id]
                room_id = session['room_id']
                
                # Determine who disconnected
                if request.sid == session['agent_sid']:
                    # Agent disconnected
                    disconnected_user = session['agent_username']
                    remaining_user = session['client_username']
                    remaining_sid = session['client_sid']
                else:
                    # Client disconnected
                    disconnected_user = session['client_username']
                    remaining_user = session['agent_username']
                    remaining_sid = session['agent_sid']
                    
                    # Return agent to available pool
                    support_type = session['support_type']
                    if session['agent_sid'] not in available_agents[support_type]:
                        available_agents[support_type].append(session['agent_sid'])
                
                # Log the disconnection
                disconnect_msg = f'{disconnected_user} has left the session'
                session['messages'].append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'content': f"SYSTEM: {disconnect_msg}"
                })
                
                # Notify remaining user
                socketio.emit('user_disconnected', {
                    'msg': disconnect_msg
                }, room=remaining_sid)
                
                # Save session log before cleaning up
                save_session_log(session_id, session)
                
                # Clean up session
                del active_sessions[session_id]
                del user_sessions[request.sid]
                if remaining_sid in user_sessions:
                    del user_sessions[remaining_sid]
                
                print(f"Session {session_id[:8]} ended: {disconnected_user} disconnected")
        
        else:
            # Check if it's an agent who was just waiting
            for support_type, agents in available_agents.items():
                if request.sid in agents:
                    agents.remove(request.sid)
                    print(f"Available {support_type} agent disconnected")
                    break

@socketio.on('message')
def handle_message(data):
    from flask import request
    
    if request.sid in user_sessions:
        session_id = user_sessions[request.sid]
        if session_id in active_sessions:
            session = active_sessions[session_id]
            room_id = session['room_id']
            
            # Determine sender
            if request.sid == session['agent_sid']:
                sender = session['agent_username']
            else:
                sender = session['client_username']
            
            # Create message content
            message_content = f"{sender}: {data['msg']}"
            
            # Log the message
            session['messages'].append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'content': message_content
            })
            
            # Broadcast message to the session room
            socketio.emit('message', {
                'msg': message_content,
                'sender': sender
            }, room=room_id)

@socketio.on('get_stats')
def handle_get_stats():
    """Admin endpoint to get current system stats"""
    stats = {
        'available_agents': {k: len(v) for k, v in available_agents.items()},
        'active_sessions': len(active_sessions),
        'sessions_detail': [
            {
                'session_id': sid[:8],
                'support_type': session['support_type'],
                'client': session['client_username'],
                'agent': session['agent_username'],
                'messages_count': len(session['messages']),
                'start_time': session['start_time']
            }
            for sid, session in active_sessions.items()
        ]
    }
    emit('stats', stats)

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5002)