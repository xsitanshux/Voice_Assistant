# Voice Assistant Application

This is a voice assistant application with a Python Flask backend for speech-to-text transcription and a React frontend for user interaction.

## Features

-   **Speech-to-Text Transcription:** Transcribes audio input into text using the backend.
-   **Interactive Frontend:** A web-based interface for interacting with the voice assistant.

## Project Structure

-   `backend.py`, `backend1.py`, `modified_backend.py`: Python Flask backend files. `modified_backend.py` is intended to be the main backend for speech transcription.
-   `frontend/`: Contains the React application for the user interface.

## Setup and Installation

### Backend

1.  Navigate to the root directory of the project.
2.  Install the required Python packages. It is recommended to use a virtual environment.
    ```bash
    pip install Flask SpeechRecognition PyAudio
    ```
    *Note: PyAudio might require additional system-level dependencies depending on your operating system.*

3.  Run the backend server:
    ```bash
    python modified_backend.py
    ```
    The backend server will typically run on `http://127.0.0.1:5000`.

### Frontend

1.  Navigate to the `frontend` directory:
    ```bash
    cd frontend
    ```
2.  Install the Node.js dependencies:
    ```bash
    npm install
    ```
3.  Start the frontend development server:
    ```bash
    npm run dev
    ```
    The frontend application will typically be accessible at `http://localhost:5173` (or another port if 5173 is in use).

## Usage

1.  Ensure both the backend and frontend servers are running.
2.  Open your web browser and navigate to the frontend application's URL (e.g., `http://localhost:5173`).
3.  Use the frontend interface to interact with the voice assistant.

## Future Improvements

-   Implement more robust error handling and logging in the backend.
-   Add more voice assistant functionalities (e.g., command recognition, natural language understanding).
-   Improve the UI/UX of the frontend.
-   Containerize the application using Docker for easier deployment.