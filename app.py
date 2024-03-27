import json
import datetime
import os
import openai
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, request, jsonify, session
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)
app.secret_key = '19092003'  # Set a secret key for session management

# Initialize Firebase Admin SDK
cred = credentials.Certificate("serviceAccountKey.json")  # Update with your service account key
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://verbify-86ea6-default-rtdb.firebaseio.com/'  # Update with your database URL
})
user_ref = db.reference('/Users')  # Reference to the directory where user information is stored

# Initialize OpenAI client
openai_api_key = "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"
client = openai.Client(api_key=openai_api_key)
thread_id = None

# Function to save user data to Firebase Realtime Database
def save_user_data(name, email, password):
    user_data = {
        'name': name,
        'email': email,
        'password': password
    }
    user_ref.push(user_data)

# Function to load assistants from Firebase Realtime Database under user's directory
def load_assistants(user_id):
    user_assistants_ref = user_ref.child(user_id).child('assistants')
    assistants = user_assistants_ref.get()
    if assistants:
        return assistants
    else:
        return {}

# Function to retrieve user data from Firebase Realtime Database by email
def get_user_by_email(email):
    if email:
        users = user_ref.order_by_child('email').equal_to(email).get()
        if users:
            # Convert the returned dictionary to a list and extract the first item
            user_data = list(users.values())[0]
            return user_data
    return None

# Route to handle user signup
@app.route('/signup', methods=['POST'])
def handle_signup():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')

    if not (name and email and password):
        return jsonify({'error': 'Name, email, and password are required fields.'}), 400

    try:
        # Check if the user already exists
        if get_user_by_email(email):
            return jsonify({'error': 'User with this email already exists.'}), 400

        # Create the user
        new_user_ref = user_ref.push()
        new_user_id = new_user_ref.key  # Get the unique ID generated by Firebase
        new_user_ref.set({
            'id': new_user_id,  # Store the user ID in the user data
            'name': name,
            'email': email,
            'password': password  # Note: Storing passwords directly like this is not secure, consider hashing them.
        })

        return jsonify({'message': 'Signup successful.', 'user_id': new_user_id}), 200
    except Exception as e:
        print("Error signing up user:", e)
        return jsonify({'error': 'An error occurred while processing the signup request.'}), 500


@app.route('/login', methods=['POST'])
def handle_login():
    email = request.form.get('email')
    password = request.form.get('password')
    print(f"Received email: {email}, password: {password}")  # Log the received data

    try:
        # Retrieve user data by email
        user_data = get_user_by_email(email)
        print(f"Retrieved user data: {user_data}")  # Log the retrieved user data

        if user_data:
            if user_data.get('password') == password:
                # Login successful, set user ID in session
                user_id = user_data.get('id')
                username = user_data.get('name')
                if user_id:
                    session['user_id'] = user_id
                    session['username'] = username
                    print(f"Set session['user_id'] to {user_id} and session['username'] to {username}")  # Log the session ID
                    # session_id = session['id']
                    # print(f"Session ID: {session_id}")  # Log the session ID
                    return jsonify({'message': 'Login successful.', 'user_id': user_id , 'username':username}), 200
                else:
                    return jsonify({'error': 'User ID not found in user data.'}), 500
            else:
                return jsonify({'error': 'Invalid email or password.'}), 401
        else:
            return jsonify({'error': 'User not found.'}), 404
    except Exception as e:
        print(f"Error logging in user: {e}")
        return jsonify({'error': 'An error occurred while processing the login request.'}), 500


@app.route('/check_session', methods=['GET'])
def check_session():
    user_id = session.get('user_id')
    if user_id:
        return jsonify({'is_logged_in': True, 'user_id': user_id}), 200
    else:
        return jsonify({'is_logged_in': False}), 401

@app.route('/create_assistant', methods=['POST'])
def handle_create_assistant():
    user_id = request.json.get('session_id')
    if not user_id:
        return jsonify({'error': 'User not logged in.'}), 401

    name = request.json.get('name')
    description = request.json.get('description')
    instructions = request.json.get('instructions')

    print('Name:', name)
    print('Description:', description)
    print('Instructions:', instructions)

    if not (name and instructions):
        return jsonify({'error': 'Name and instructions are required fields.'}), 400

    try:
        # Create the assistant
        assistant = client.beta.assistants.create(
            name=name,
            # description=description,
            instructions=instructions,
            tools=[{"type": "code_interpreter"}],
            model="gpt-3.5-turbo",
        )

        assistant_id = assistant.id
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Store assistant information in Firebase under user's directory
        assistants_ref = user_ref.child(user_id).child('assistants')
        assistant_data = {
            'assistant_id': assistant_id,
            'name': name,
            'description': description,
            'instructions': instructions,
            'created_at': created_at
        }
        assistants_ref.push(assistant_data)

        return jsonify({'message': 'Assistant created successfully.', 'assistant_id': assistant_id}), 200
    except Exception as e:
        print("Error creating assistant:", e)
        return jsonify({'error': 'Failed to create assistant.'}), 500
        

@app.route('/assistants', methods=['POST'])
def get_user_assistants():
    # Check if user is logged in
    user_id = request.json.get('session_id')
    print('Received session ID:', user_id) # Add this line
    if not user_id:
        return jsonify({'error': 'User not logged in.'}), 401

    try:
        # Load assistants from Firebase Realtime Database for the current user
        assistants = load_assistants(user_id)

        # Convert the assistants dictionary to a list for serialization
        assistants_list = [{'assistant_id': key, **value} for key, value in assistants.items()]

        return jsonify(assistants_list), 200
    except Exception as e:
        print(f"Error retrieving assistants: {e}")
        return jsonify({'error': 'An error occurred while retrieving assistants.'}), 500

# Function to retrieve assistant ID based on user ID
def get_assistant_id(user_id):
    ref = db.reference(f'/Users/{user_id}/assistants')
    assistant_info = ref.get()
    if assistant_info:
        for assistant_data in assistant_info.values():
            if isinstance(assistant_data, dict) and 'assistant_id' in assistant_data:
                return assistant_data['assistant_id']  # Extract assistant ID from the dictionary
    return None

@app.route('/send_message', methods=['POST'])
def send_message():
    global thread_id
    user_id = request.headers.get('session_id') 
    assistant_id = request.json.get('assistant_id')
    print(f"{assistant_id}")
    print(f"{user_id}")# Retrieve user ID from session
    if not user_id:
        return jsonify({'message': "User not logged in."}), 401

    message = request.json['message']
    print("Received message from user:", user_id, message)

    if not message:
        return jsonify({'message': "Please provide a valid message."}), 400

    # assistant_id = get_assistant_id(user_id)
    if assistant_id is None:
        return jsonify({'message': "Assistant ID not found for the user."}), 404

    if thread_id is None:
        # Create a thread for the selected assistant
        thread = client.beta.threads.create()
        thread_id = thread.id
        print("Thread created:", thread_id)

    try:
        # Add the message to the thread
        message = client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)
        print("Message added to thread:", message.id)

        # Create a run with the assistant
        run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
        print("Run created:", run.id)

        # Monitor the status of the run
        print("Monitoring run status...")
        while True:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            print("Run status:", run.status)
            if run.status in ['completed', 'failed', 'cancelled']:
                break
            time.sleep(1)

        # Once the run is completed, retrieve the assistant's response
        if run.status == 'completed':
            assistant_response_message = retrieve_assistant_response(thread_id)
            print("Assistant response:", assistant_response_message)
            return jsonify({'message': assistant_response_message}), 200
        else:
            return jsonify({'message': "An error occurred while processing the message. Please try again later."}), 500
    except Exception as e:
        print("Error:", e)
        return jsonify({'message': "An error occurred while processing the message. Please try again later."}), 500

def retrieve_assistant_response(thread_id):
    try:
        print("Retrieving assistant response for thread:", thread_id)
        response = client.beta.threads.messages.list(thread_id=thread_id)
        print("Retrieved messages:", response.data)
        assistant_messages = []
        for msg in response.data[::-1]:  # Iterate in reverse order
            print("Processing message:", msg)
            print("Message role:", msg.role)
            if msg.role == "assistant":
                assistant_messages.append(msg.content[0].text.value)

        if assistant_messages:
            assistant_response = assistant_messages[-1]
            print("Assistant response:", assistant_response)
            return assistant_response
        else:
            return "No assistant response found"
    except Exception as e:
        print("Error retrieving assistant response:", e)
        return "An error occurred while processing the message. Please try again later."
    
    # Route to log user activity
@app.route('/log_activity', methods=['POST'])
def log_activity():
    user_id =  request.headers.get('session_id')   # Retrieve user ID from session
    if not user_id:
        return jsonify({'message': "User not logged in."}), 401

    activity = request.json.get('activity')
    if not activity:
        return jsonify({'message': "Please provide activity data."}), 400

    # Log the activity to Firebase or any other storage mechanism
    log_ref = db.reference(f'/UserActivity/{user_id}')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_ref.push({'timestamp': timestamp, 'activity': activity})

    return jsonify({'message': "Activity logged successfully."}), 200


if __name__ == '__main__':
    app.run(debug=True)
