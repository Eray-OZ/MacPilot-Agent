# Remote Mac Control - System Architecture (ARCHITECTURE.md)

This document explains how natural language commands sent from the Android mobile app (Frontend) are processed on the Mac computer (Backend), detailing the technologies used and the request lifecycle.

---

## 1. Overall Architectural Structure

The system consists of two core components:
1. **Android Frontend (Kotlin, Jetpack Compose, Retrofit)**: A modern, asynchronous mobile client where users input natural language commands and view the results.
2. **Mac Backend (Python, FastAPI, Official Google GenAI SDK, Gemini 3.5 Flash API)**: An intelligent agent server that interprets natural language from the Android device, generates system commands/AppleScripts, and executes them on macOS.

### Component Diagram

```
+-----------------------------------+
|        Android Mobile App         | <--- (Same Wi-Fi Network)
| - Jetpack Compose (UI)            |
| - ViewModel (State Management)    |
| - Retrofit (HTTP POST Request)    |
+-----------------------------------+
                 |
                 | HTTP POST /run-agent {"command": "open Spotify"}
                 v
+-----------------------------------+
|        Mac FastAPI Server         |
| - FastAPI (API Layer)             |
| - Uvicorn (ASGI Server)           |
+-----------------------------------+
                 |
                 | Passes Command to Agent
                 v
+-----------------------------------+
|     Official Google GenAI SDK     | <--- Structured Output (JSON)
| - Gemini 3.5 Flash Model          |
| - response_schema (Pydantic)      |
+-----------------------------------+
                 |
                 | Pydantic Output Parsing (action, app_name, url, value, explanation)
                 v
+-----------------------------------+
|     execute_app_control Function  |
| - Python Subprocess               |
| - MacOS Terminal / AppleScript    |
| - Volume, Brightness, Lock, Media |
+-----------------------------------+
                 |
                 | Executes macOS System Commands
                 v
+-----------------------------------+
|             macOS OS              |
| - open -a "Spotify"               |
| - osascript -e 'quit app ...'     |
| - pmset displaysleepnow           |
| - AppleScript System Volume/Media |
+-----------------------------------+
```

---

## 2. Request Lifecycle & Data Flow (Sequence Diagram)

The diagram below illustrates the step-by-step lifecycle of a request, from when a user types a command like "open Spotify" to the application opening and the response appearing on the mobile screen:

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Android as Android App (Compose & Retrofit)
    participant API as FastAPI Backend (Mac)
    participant SDK as Official Google GenAI SDK
    participant OS as macOS System

    User->>Android: Types "open Spotify" and presses Send
    Note over Android: CircularProgressIndicator is displayed (Loading...)
    Android->>API: POST /run-agent {"command": "open Spotify"}
    API->>SDK: Calls client.models.generate_content with command, Pydantic schema, and gemini-3.5-flash
    SDK-->>API: Returns structured JSON (action="set_volume", value=20, explanation="Setting volume to 20%!")
    
    rect rgb(240, 248, 255)
        Note over API, OS: System Action Execution Phase
        API->>OS: Runs via Subprocess: osascript -e "set volume output volume 20"
        OS-->>API: Command execution result (Success / Error)
    end

    alt On Success
        API-->>Android: HTTP 200 {"response": "Opening Spotify for you!", "status": "success"}
    else On Error
        API-->>Android: HTTP 200 {"response": "Error details...", "status": "error"}
    end
    
    Note over Android: CircularProgressIndicator hidden, response added to history
    Android-->>User: Displays result on UI
```

---

## 3. Detailed Component Responsibilities

### A. Android Frontend
- **User Interface (Jetpack Compose)**: A state-of-the-art UI utilizing Material 3 components. It provides a clean, premium visual style with a dark mode theme and beautiful gradient backdrops.
- **Asynchronous Processing (Coroutines & ViewModel)**: To prevent UI freezes, all network requests are executed on background threads (`Dispatchers.IO`). ViewModel handles UI state management reactively using `uiState` (Idle, Loading, Success, Error).
- **Dynamic IP Configuration & Retrofit Client**: Facilitates seamless JSON communication with the FastAPI server running on the Mac. Users can dynamically configure the target local IP address from the settings panel.

### B. Mac Backend (Python)
- **FastAPI / Uvicorn**: A high-performance, modern web framework with support for Python type hinting, offering automated Swagger UI documentation out of the box.
- **Official Google GenAI SDK (`google-genai`)**:
  - Directly leverages Google's flagship fast model, **`gemini-3.5-flash`**.
  - **Structured Outputs (Pydantic Schema)**: Uses `types.GenerateContentConfig` with `response_mime_type="application/json"` and `response_schema=AppControlAction` to guarantee 100% reliable, typed JSON parsing.
- **Application Management System (`execute_app_control`)**:
  - Uses Python's `subprocess` module to run shell commands securely on macOS.
  - **Opening Apps**: Triggers `open -a "{Application Name}"` to launch programs.
  - **Closing Apps**: Triggers an AppleScript command: `osascript -e 'quit application "{Application Name}"'`. This method ensures clean and graceful termination of target apps, saving unsaved progress.
  - **Opening URLs in Browser**: Triggers `open "{URL}"` (for system default browser) or `open -a "{Browser Name}" "{URL}"` (for specific browsers). It automatically normalizes raw web addresses (e.g. `google.com` -> `https://google.com`) before execution.
  - **Volume & Mute Control**: Adjusts system volume using `osascript -e "set volume output volume {value}"` and toggles mute/unmute status securely.
  - **Screen Lock & Sleep**: Instantly locks the Mac screen using `pmset displaysleepnow` or puts the Mac to sleep via AppleScript.
  - **Brightness Adjustment**: Simulates macOS Brightness Up (F14) and Brightness Down (F15) keys using native System Events.
  - **Media Control**: Intelligently auto-detects running media players (Spotify or Apple Music) and sends play/pause, next track, or previous track commands via AppleScript.
