import os
from typing import Final
from dotenv import load_dotenv

# Load .env first so os.getenv reads values from it if present
load_dotenv()

# Load secrets from environment variables for safety
TOKEN: Final = os.getenv("WAYDII_TOKEN")
BOT_USERNAME: Final = os.getenv("WAYDII_BOT_USERNAME", "waydii_waxwalba_bot")
CHANNEL_USERNAME: Final = os.getenv("WAYDII_CHANNEL_USERNAME", "@waydii_waxwalba")

if not TOKEN:
	raise RuntimeError(
		"Environment variable WAYDII_TOKEN is not set. "
		"Set WAYDII_TOKEN or create a local .env file and load it before running."
	)
