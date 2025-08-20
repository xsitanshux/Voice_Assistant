import win32com.client
import os
import time
import logging
import json
import pythoncom
import uuid
from typing import List, Dict, Optional
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('submission_mailer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class SubmissionMailer:
    def __init__(self, watch_folder: str, recipient_email: str, subject_prefix: str = "Submission: "):
        self.watch_folder = os.path.abspath(os.path.normpath(watch_folder))
        self.recipient_email = recipient_email
        self.subject_prefix = subject_prefix
        self.tracker_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submission_tracker.json")
        self.uploaded_files = self._load_tracker()
        
        # Create watch folder if it doesn't exist
        if not os.path.exists(self.watch_folder):
            os.makedirs(self.watch_folder)
            logging.info(f"Created watch folder: {self.watch_folder}")

    def _load_tracker(self) -> Dict[str, Dict]:
        """Load the JSON tracker file or create it if it doesn't exist"""
        if os.path.exists(self.tracker_file):
            try:
                with open(self.tracker_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logging.error("Error parsing tracker file. Creating new tracker.")
                return {}
        else:
            logging.info("Tracker file not found. Creating new tracker.")
            return {}

    def _save_tracker(self) -> None:
        """Save the tracker to JSON file"""
        try:
            with open(self.tracker_file, 'w') as f:
                json.dump(self.uploaded_files, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving tracker file: {str(e)}")

    def assign_submission_id(self, file_path: str) -> Optional[str]:
        """Assign a unique UUID as the submission ID for the file"""
        if file_path in self.uploaded_files and self.uploaded_files[file_path].get("sent_time"):
            logging.info(f"File {file_path} has already been sent. Skipping.")
            return None
        
        if file_path not in self.uploaded_files:
            submission_id = str(uuid.uuid4())
            self.uploaded_files[file_path] = {
                "submission_id": submission_id,
                "filename": os.path.basename(file_path),
                "sent_time": None
            }
            self._save_tracker()
        return self.uploaded_files[file_path]["submission_id"]

    def get_pending_submissions(self) -> List[str]:
        """Get list of files in watch folder that haven't been uploaded yet"""
        pending_files = []
        
        try:
            for filename in os.listdir(self.watch_folder):
                file_path = os.path.join(self.watch_folder, filename)
                
                # Skip directories and the tracker file
                if os.path.isdir(file_path) or filename == os.path.basename(self.tracker_file):
                    continue
                
                # Skip already uploaded files
                if self.uploaded_files.get(file_path, {}).get("sent_time"):
                    continue
                
                pending_files.append(file_path)
        
        except Exception as e:
            logging.error(f"Error scanning directory: {str(e)}")
        
        return pending_files

    def send_email(self, file_path: str) -> bool:
        """Send an email with the file as an attachment"""
        submission_id = self.assign_submission_id(file_path)
        if not submission_id:
            return False
        filename = os.path.basename(file_path)
        
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)  # 0: olMailItem
            
            mail.To = self.recipient_email
            mail.Subject = f"{self.subject_prefix}{submission_id}"
            mail.Body = f"Attached is file {filename} for submission {submission_id}."
            
            # Add attachment
            mail.Attachments.Add(file_path)
            
            # Send the email
            mail.Send()
            
            logging.info(f"Successfully sent email for {filename} with submission ID {submission_id}")
            
            # Update tracker
            self.uploaded_files[file_path]["sent_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_tracker()
            
            return True
            
        except Exception as e:
            logging.error(f"Error sending email for {filename}: {str(e)}")
            return False
        finally:
            pythoncom.CoUninitialize()

    def process_pending_submissions(self) -> int:
        """Process all pending submission files"""
        pending_files = self.get_pending_submissions()
        
        if not pending_files:
            logging.info("No new submission files to process")
            return 0
            
        successful_count = 0
        for file_path in pending_files:
            if self.send_email(file_path):
                successful_count += 1
                
        logging.info(f"Processed {successful_count} out of {len(pending_files)} submission files")
        return successful_count


def main():
    # Get user input for folder and email
    watch_folder = input("Enter the directory to watch for submissions: ").strip().strip('"')
    watch_folder = os.path.normpath(watch_folder)
    recipient_email = input("Enter the recipient email: ").strip()
    
    try:
        mailer = SubmissionMailer(watch_folder, recipient_email)
        
        print("Submission Mailer started")
        print(f"Watching folder: {watch_folder}")
        print(f"Files will be sent to: {recipient_email}")
        print("Press Ctrl+C to stop...")
        
        while True:
            count = mailer.process_pending_submissions()
            if count > 0:
                print(f"Sent {count} submission files")
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        print("\nStopping Submission Mailer...")
        print("Mailer stopped successfully.")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
