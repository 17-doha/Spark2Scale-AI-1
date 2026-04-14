import uvicorn
import os
import sys

if __name__ == "__main__":
    # Add the current directory to sys.path to ensure 'app' module is found
    sys.path.append(os.getcwd())
    
    print("🚀 Starting Spark2Scale AI API Server...")
    print("📝 Documentation available at: http://localhost:8000/docs")
    
    # Run the Uvicorn server
    # We reference the app via import string "app.api.main:app"
    try:
        uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=True)
    except ImportError as e:
        print(f"[ERROR] Error importing app: {e}")
        print("Please ensure you are running this script from the project root directory.")
    except Exception as e:
        print(f"[ERROR] Server failed to start: {e}")