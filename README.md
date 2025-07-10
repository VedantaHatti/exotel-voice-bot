Step 1: Download Project



git clone https://github.com/yourusername/exotel-voice-bot.git
cd exotel-voice-bot


Step 2: Create Environment File

Create a file called .env in the project folder with your API keys:
envEXOTEL_API_KEY=your_exotel_api_key_here
EXOTEL_API_TOKEN=your_exotel_api_token_here
EXOTEL_ACCOUNT_SID=your_exotel_account_sid_here
EXOTEL_CALLER_ID=your_exotel_caller_id_here
EXOTEL_APP_ID=your_exotel_app_id_here
OPENAI_API_KEY=your_openai_api_key_here
DEEPGRAM_API_KEY=your_deepgram_api_key_here
CARTESIA_API_KEY=your_cartesia_api_key_here

Step 3: Build and Run

# Build the Docker container
docker build -t voice-bot .

# Run the container
docker run -d -p 8765:8765 --env-file .env voice-bot
