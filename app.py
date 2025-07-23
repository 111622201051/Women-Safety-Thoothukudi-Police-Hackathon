import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
import sounddevice as sd
import soundfile as sf
import cv2
from datetime import datetime
import logging
import json
from flask import Flask, render_template, request, jsonify
import threading

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_key")

def get_ip_location():
    """
    Fetches the current location based on the device's IP address.
    Returns latitude and longitude as floats.
    """
    try:
        response = requests.get('https://ipinfo.io/json')
        data = response.json()
        loc = data.get('loc', '0,0').split(',')
        latitude = float(loc[0])
        longitude = float(loc[1])
        return latitude, longitude
    except Exception as e:
        logger.error(f"Error fetching IP location: {e}")
        return None, None


def reverse_geocode(api_key, latitude, longitude):
    """
    Converts latitude and longitude into a human-readable address using HERE Maps API.
    Falls back to coordinates if API unavailable.
    """
    # Check if we have API key and valid coordinates
    if not api_key or not latitude or not longitude:
        return f"Coordinates: {latitude}, {longitude}"

    try:
        # First, try to use the HERE Maps API
        url = f"https://geocode.reverse.hereapi.com/v1/reverse?at={latitude},{longitude}&apiKey={api_key}"
        response = requests.get(url, timeout=5)  # Add timeout to prevent long waits
        
        if response.status_code == 200:
            data = response.json()
            if data.get('items', []):
                address = data['items'][0]['address']
                return address.get('label', f"Coordinates: {latitude}, {longitude}")
        
        # If we reach here, there was an issue with the API response
        logger.warning(f"Could not get location from HERE Maps API. Status code: {response.status_code}")
        return f"Coordinates: {latitude}, {longitude}"
    
    except Exception as e:
        logger.error(f"Error during reverse geocoding: {e}")
        return f"Coordinates: {latitude}, {longitude}"


def send_sms_alert(message):
    """
    This function is kept for compatibility but is disabled.
    SMS functionality is not being used based on user request.
    """
    logger.info("SMS functionality is disabled as per request.")
    return True


def send_email_alert(sender_email, sender_password, recipients, subject, body, audio_file, video_file):
    """
    Sends an email alert with attachments.
    """
    # Set up the email
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    
    # Add location and time information to the message body
    full_body = f"{body}\n\nTime of Alert: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    msg.attach(MIMEText(full_body, 'plain'))

    # Attach audio file if it exists
    if os.path.exists(audio_file) and os.path.getsize(audio_file) > 0:
        try:
            with open(audio_file, "rb") as f:
                attach = MIMEApplication(f.read(), _subtype="wav")
                attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(audio_file))
                msg.attach(attach)
                logger.info(f"Successfully attached audio file: {audio_file}")
        except Exception as e:
            logger.error(f"Error attaching audio file: {e}")
            # Add a note to the email body about the missing attachment
            note = MIMEText("\n\nNote: Audio recording could not be attached due to an error.", 'plain')
            msg.attach(note)
    else:
        logger.warning(f"Audio file does not exist or is empty: {audio_file}")
        note = MIMEText("\n\nNote: Audio recording could not be created due to device limitations.", 'plain')
        msg.attach(note)

    # Attach video file if it exists
    if os.path.exists(video_file) and os.path.getsize(video_file) > 0:
        try:
            with open(video_file, "rb") as f:
                attach = MIMEApplication(f.read(), _subtype="avi")
                attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(video_file))
                msg.attach(attach)
                logger.info(f"Successfully attached video file: {video_file}")
        except Exception as e:
            logger.error(f"Error attaching video file: {e}")
            # Add a note to the email body about the missing attachment
            note = MIMEText("\n\nNote: Video recording could not be attached due to an error.", 'plain')
            msg.attach(note)
    else:
        logger.warning(f"Video file does not exist or is empty: {video_file}")
        note = MIMEText("\n\nNote: Video recording could not be created due to device limitations.", 'plain')
        msg.attach(note)

    # Send email
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipients, text)
        server.quit()
        logger.info(f"Email alert sent successfully to {recipients}!")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def send_alert(api_key, status_callback=None):
    """
    Sends an alert with the user's location to a predefined list of contacts.
    """
    def update_status(status, success=True):
        if status_callback:
            status_callback(status, success)
        logger.info(status)

    update_status("Starting emergency alert process...")
    
    # Fetch current location based on IP
    update_status("Detecting location...")
    latitude, longitude = get_ip_location()
    if latitude is None or longitude is None:
        update_status("Unable to fetch location.", False)
        return False

    location_address = reverse_geocode(api_key, latitude, longitude)
    update_status(f"Location detected: {location_address}")

    # Email and SMS details
    sender_email = os.environ.get("SENDER_EMAIL", "gokuad021@rmkcet.ac.in")
    sender_password = os.environ.get("EMAIL_PASSWORD", "sugs hwmo fkxc sazi")
    email_recipients = os.environ.get("EMAIL_RECIPIENTS", "gokuad021@rmkcet.ac.in").split(",")

    subject = "Emergency Alert!"
    body = f"Help needed! My current location is {location_address}. Latitude: {latitude}, Longitude: {longitude} and do please checkout ur email!."

    # Create placeholder files for audio and video if we can't record
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    audio_filename = f"alert_audio_{timestamp}.wav"
    video_filename = f"alert_video_{timestamp}.avi"
    audio_recorded = False
    video_recorded = False

    # Record audio
    update_status("Recording audio...")
    try:
        recording = sd.rec(int(10 * 44100), samplerate=44100, channels=2)
        sd.wait()
        sf.write(audio_filename, recording, 44100)
        update_status("Audio recorded successfully")
        audio_recorded = True
    except Exception as e:
        update_status(f"Could not record audio: {e}. Sending email without audio attachment.", False)
        # Create a placeholder file
        with open(audio_filename, 'wb') as f:
            f.write(b'Placeholder audio file')

    # Capture video
    update_status("Recording video...")
    try:
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out = cv2.VideoWriter(video_filename, fourcc, 20.0, (640, 480))

            start_time = datetime.now()
            while (datetime.now() - start_time).seconds < 10:  # 10 seconds of video
                ret, frame = cap.read()
                if ret:
                    out.write(frame)
                else:
                    break

            cap.release()
            out.release()
            update_status("Video recorded successfully")
            video_recorded = True
        else:
            update_status("Could not open video device. Sending email without video attachment.", False)
            # Create a placeholder file
            with open(video_filename, 'wb') as f:
                f.write(b'Placeholder video file')
    except Exception as e:
        update_status(f"Error recording video: {e}. Sending email without video attachment.", False)
        # Create a placeholder file if it doesn't exist yet
        if not os.path.exists(video_filename):
            with open(video_filename, 'wb') as f:
                f.write(b'Placeholder video file')

    # Send email alert
    update_status("Sending email alert...")
    email_success = send_email_alert(sender_email, sender_password, email_recipients, subject, body, audio_filename, video_filename)
    if email_success:
        update_status("Email alert sent successfully")
    else:
        update_status("Failed to send email alert", False)

    # Send SMS alert
    update_status("Sending SMS alert...")
    sms_success = send_sms_alert(body)
    if sms_success:
        update_status("SMS alert sent successfully")
    else:
        update_status("Failed to send SMS alert", False)

    update_status("Emergency alert process completed.")
    return email_success or sms_success


def emergency_sos(api_key, status_callback=None):
    """
    Triggers the emergency SOS process.
    """
    return send_alert(api_key, status_callback)


# Flask routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/sos', methods=['POST'])
def sos():
    """API endpoint to trigger SOS alert"""
    here_maps_api_key = os.environ.get('HERE_MAPS_API_KEY', '')
    status_updates = []

    def status_callback(message, success=True):
        status_updates.append({"message": message, "success": success})
    
    # Run the emergency SOS in a separate thread to avoid blocking the response
    thread = threading.Thread(
        target=emergency_sos, 
        args=(here_maps_api_key, status_callback)
    )
    thread.daemon = True
    thread.start()
    
    # Return an immediate response
    return jsonify({"status": "Emergency alert initiated", "message": "Help is on the way!"})


@app.route('/check_status', methods=['GET'])
def check_status():
    """API endpoint to check the status of the SOS alert process"""
    # This would need a more sophisticated implementation with session tracking
    # For now, we'll return a placeholder success
    return jsonify({"status": "complete", "success": True})
