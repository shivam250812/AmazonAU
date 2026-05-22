import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def send_email_notification(subject: str, message: str):
    """
    Sends an email notification using SMTP.
    Requires SENDER_EMAIL, SENDER_PASSWORD, and RECEIVER_EMAIL to be set in .env.
    """
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    sender_email = os.getenv("SENDER_EMAIL") or os.getenv("SMTP_USERNAME")
    sender_password = os.getenv("SENDER_PASSWORD") or os.getenv("SMTP_PASSWORD")
    if sender_password:
        sender_password = sender_password.replace(" ", "")
    receiver_email = os.getenv("RECEIVER_EMAIL")

    if not sender_email or not sender_password or not receiver_email:
        print(" Notification skipped: Email credentials not fully configured in .env.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject

        msg.attach(MIMEText(message, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f" Notification sent to {receiver_email}: {subject}")
    except Exception as e:
        print(f" Failed to send notification email: {e}")
