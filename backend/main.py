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
    action: str = Field(description="Action to perform. Can be 'open' (to open an app), 'close' (to quit an app), or 'open_url' (to open a website in a browser).")
    app_name: str = Field(description="Target application name (e.g., 'Spotify', 'Google Chrome', 'Safari'). Can be left empty for 'open_url' if no specific browser is requested.")
    url: Optional[str] = Field(default=None, description="The complete URL to open if action is 'open_url' (e.g., 'https://www.google.com'). Should be null/empty otherwise.")
    explanation: str = Field(description="A short, friendly, and natural English confirmation sentence for the user (e.g., 'Opening youtube.com in Google Chrome for you!')")

# Validate API key and initialize client
api_key = os.getenv("GEMINI_API_KEY")
client = None

if api_key and api_key != "your_gemini_api_key_here":
    print(f"INFO: GEMINI_API_KEY successfully loaded. (Visible part: {api_key[:8]}...)")
    client = genai.Client(api_key=api_key)
else:
    print("WARNING: GEMINI_API_KEY not found or left as default in .env file!")

# Core function to execute system commands on macOS
def execute_app_control(action: str, app_name: str, url: Optional[str] = None) -> tuple[bool, str]:
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
    else:
        return False, f"Invalid action '{action}'. Only 'open', 'close', or 'open_url' are supported."


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
            "and determine whether to open an app, close an app, or open a URL in a browser.\n\n"
            "Command to analyze: '{command}'\n\n"
            "Rules:\n"
            "1. If the user wants to open an application, set action='open'. If they want to close it, set action='close'.\n"
            "2. If the user wants to open a website or link, set action='open_url' and put the full URL (e.g., 'https://youtube.com' or 'google.com') in the url field.\n"
            "3. Correctly identify the application or browser name (e.g., 'open Spotify' -> 'Spotify', 'open youtube in Chrome' -> 'Google Chrome', 'open in Safari' -> 'Safari').\n"
            "4. Write a short, friendly, and natural English confirmation sentence in the explanation field (e.g., 'Opening youtube.com in Google Chrome for you!')."
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
        success, exec_msg = execute_app_control(action_result.action, action_result.app_name, action_result.url)

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
