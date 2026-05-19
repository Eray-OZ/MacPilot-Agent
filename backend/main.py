import os
import subprocess
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI application
app = FastAPI(
    title="Remote Mac Control API",
    description="Backend API powered by official Google GenAI SDK and Gemini 3.5 Flash to control Mac via Android commands.",
    version="1.0.0"
)

# Enable CORS for local network communication and testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incoming command request schema
class CommandRequest(BaseModel):
    command: str = Field(..., description="Natural language command to execute on Mac (e.g., 'open Spotify')", json_schema_extra={"example": "Open Spotify"})

# Outgoing agent response schema
class AgentResponse(BaseModel):
    response: str = Field(..., description="Response text returned by the agent")
    status: str = Field(..., description="Execution status ('success' or 'error')")

# Structured output schema for Gemini model
class AppControlAction(BaseModel):
    action: str = Field(description="Action to perform. Can be 'open' (open an app), 'close' (quit an app), 'open_url' (open a URL in browser), 'set_volume' (set audio volume level), 'mute' (mute audio), 'unmute' (unmute audio), 'lock_screen' (lock macOS session), 'sleep' (put Mac to sleep), 'play_pause' (toggle media playback), 'next_track' (skip to next track), 'previous_track' (go back to previous track), 'brightness_up' (increase screen brightness), or 'brightness_down' (decrease screen brightness).")
    app_name: str = Field(default="", description="Target application name (e.g., 'Spotify', 'Google Chrome', 'Safari'). Leave empty if not controlling a specific app.")
    url: Optional[str] = Field(default=None, description="The complete URL to open if action is 'open_url'. Should be null/empty otherwise.")
    value: Optional[int] = Field(default=None, description="Numeric parameter for actions (e.g., volume level from 0 to 100 for 'set_volume'). Should be null otherwise.")
    explanation: str = Field(description="A short, friendly, and natural English confirmation sentence for the user (e.g., 'Setting system volume to 40% for you!').")

# Validate API key and initialize client
api_key = os.getenv("GEMINI_API_KEY")
client = None

if api_key and api_key != "your_gemini_api_key_here":
    print(f"INFO: GEMINI_API_KEY successfully loaded. (Visible part: {api_key[:8]}...)")
    client = genai.Client(api_key=api_key)
else:
    print("WARNING: GEMINI_API_KEY not found or left as default in .env file!")

# Core function to execute system commands on macOS
def execute_app_control(action: str, app_name: str, url: Optional[str] = None, value: Optional[int] = None) -> tuple[bool, str]:
    action = action.strip().lower()
    app_name = app_name.strip() if app_name else ""

    if action == "open":
        if not app_name:
            return False, "Target application name is missing."
        try:
            # Execute open -a "Application Name" command
            subprocess.run(
                ["open", "-a", app_name],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"'{app_name}' opened successfully."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to open '{app_name}'. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "close":
        if not app_name:
            return False, "Target application name is missing."
        try:
            # Cleanly quit application using AppleScript
            script = f'quit application "{app_name}"'
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"'{app_name}' closed successfully."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to close '{app_name}'. Please check macOS System Settings -> Privacy & Security -> Automation/Accessibility permissions. Details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "open_url":
        if not url:
            return False, "Target URL is missing."
        
        # Prepend https if protocol is missing
        url_str = url.strip()
        if not url_str.startswith(("http://", "https://")):
            url_str = "https://" + url_str

        try:
            browser_mapping = {
                "safari": "Safari",
                "google chrome": "Google Chrome",
                "chrome": "Google Chrome",
                "firefox": "Firefox",
                "opera": "Opera",
                "arc": "Arc"
            }
            target_browser = None
            if app_name:
                app_name_lower = app_name.lower().strip()
                for key, val in browser_mapping.items():
                    if key in app_name_lower:
                        target_browser = val
                        break

            if target_browser:
                # open -a "Browser Name" "URL"
                subprocess.run(
                    ["open", "-a", target_browser, url_str],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return True, f"Successfully opened '{url_str}' in {target_browser}."
            else:
                # open "URL" (Default system browser)
                subprocess.run(
                    ["open", url_str],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return True, f"Successfully opened '{url_str}' in default browser."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to open URL. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "set_volume":
        if value is None:
            return False, "Volume level value is missing."
        try:
            # Constrain volume between 0 and 100
            val = max(0, min(100, value))
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {val}"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"System volume set to {val}%."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to set volume. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "mute":
        try:
            subprocess.run(
                ["osascript", "-e", "set volume with output muted"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "System volume muted."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to mute system volume. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "unmute":
        try:
            subprocess.run(
                ["osascript", "-e", "set volume without output muted"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "System volume unmuted."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to unmute system volume. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "lock_screen":
        try:
            # Secure display sleep immediately locks macOS screen if set in system preferences
            subprocess.run(
                ["pmset", "displaysleepnow"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "macOS screen locked successfully."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to lock macOS screen. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "sleep":
        try:
            subprocess.run(
                ["osascript", "-e", "tell application \"System Events\" to sleep"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "Mac set to sleep mode successfully."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to sleep Mac. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "brightness_up":
        try:
            # Simulates pressing the Brightness Up key (key code 144) 3 times
            subprocess.run(
                ["osascript", "-e", "tell application \"System Events\" to repeat 3 times\nkey code 144\nend repeat"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "System brightness increased."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to increase screen brightness. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action == "brightness_down":
        try:
            # Simulates pressing the Brightness Down key (key code 145) 3 times
            subprocess.run(
                ["osascript", "-e", "tell application \"System Events\" to repeat 3 times\nkey code 145\nend repeat"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "System brightness decreased."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to decrease screen brightness. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    elif action in ("play_pause", "next_track", "previous_track"):
        # Map actions to target AppleScript functions
        media_mapping = {
            "play_pause": "playpause",
            "next_track": "next track",
            "previous_track": "previous track"
        }
        cmd = media_mapping[action]
        script = f"""
        if application "Spotify" is running then
            tell application "Spotify" to {cmd}
        else if application "Music" is running then
            tell application "Music" to {cmd}
        else
            error "Neither Spotify nor Apple Music is running."
        end if
        """
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True
            )
            action_friendly = action.replace("_", " ")
            return True, f"Media command '{action_friendly}' executed successfully."
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return False, f"Failed to control media playback. Error details: {error_msg}"
        except Exception as e:
            return False, f"An unexpected error occurred: {str(e)}"

    else:
        return False, f"Invalid action '{action}'. System control action is not supported."


@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Remote Mac Control API powered by official Gemini 3.5 Flash is running. Ready for Android connections.",
        "api_docs": "/docs"
    }


@app.post("/run-agent", response_model=AgentResponse)
async def run_agent(request: CommandRequest):
    """
    Main endpoint that processes natural language command using official 'google-genai' SDK 
    and 'gemini-3.5-flash' model, then executes the structured action on macOS.
    """
    global client
    
    # Hot-reload check for GEMINI_API_KEY at runtime if client is not initialized
    if not client:
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and api_key != "your_gemini_api_key_here":
            client = genai.Client(api_key=api_key)
        else:
            raise HTTPException(
                status_code=500,
                detail="GEMINI_API_KEY not found! Please define your Google Gemini API key in the .env file."
            )

    try:
        # Prepare instruction prompt for Gemini 3.5 Flash model
        prompt = (
            "You are a macOS remote control assistant. Your task is to analyze the user's natural language command "
            "and determine the appropriate action to take.\n\n"
            "Command to analyze: '{command}'\n\n"
            "Rules:\n"
            "1. App control: If user wants to open an app, set action='open' and specify app_name. If they want to close it, set action='close'.\n"
            "2. URL control: If user wants to open a website, set action='open_url', put the URL in the url field (e.g. 'google.com'), and specify browser name in app_name if mentioned.\n"
            "3. Volume control: If user wants to change volume, set action='set_volume' and parse the integer value (0 to 100) into the value field. For mute/unmute, set action='mute' or action='unmute'.\n"
            "4. Screen & Power: If user wants to lock the screen, set action='lock_screen'. If they want to sleep the Mac, set action='sleep'.\n"
            "5. Brightness control: If user wants screen brighter/darker, set action='brightness_up' or action='brightness_down'.\n"
            "6. Media control: If user wants to toggle play/pause, play next track, or go back to the previous track on Spotify or Apple Music, set action='play_pause', action='next_track', or action='previous_track'.\n"
            "7. Output explanation: Write a friendly English confirmation sentence in the explanation field (e.g. 'Muting your Mac sound now.', 'Setting volume to 50% for you!')."
        ).format(command=request.command)

        # Call Gemini 3.5 Flash model with structured output configuration
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AppControlAction,
                temperature=0.0,
            ),
        )

        # Parse JSON response text into Pydantic model
        action_result = AppControlAction.model_validate_json(response.text)

        # Execute target action on macOS
        success, exec_msg = execute_app_control(
            action_result.action, 
            action_result.app_name, 
            action_result.url, 
            action_result.value
        )

        if success:
            return AgentResponse(response=action_result.explanation, status="success")
        else:
            return AgentResponse(response=exec_msg, status="error")

    except Exception as e:
        # Handle exceptions gracefully and return error response
        return AgentResponse(
            response=f"An error occurred while executing the command on the server: {str(e)}",
            status="error"
        )

# Direct execution entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
