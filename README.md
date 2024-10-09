# IDSafe
IDSafe is a discord KYC bot for verifying discord users on 18+ discord servers


## installation
# Discord Human Verification Bot

This is a Discord bot built for human verification using ID documents and selfies. The bot supports automatic and manual verification by staff members, leveraging an external API to analyze ID images and selfies for validity.

## Features

- **Automated Verification**: Uses an API to verify if an ID is real and matches the user's selfie.
- **Manual Verification**: Allows staff members to manually review cases when automated verification is unavailable or turned off.
- **Server-Specific Setup**: The bot can be configured for each Discord server to use a specific channel for verification and assign a verified role upon success.
- **Staff Command Access**: Restricts sensitive commands to authorized staff members only.
- **Logging**: Logs API requests and responses as well as important actions like role assignments for easy debugging.

## Prerequisites

- Python 3.8+
- Discord bot token
- API key for ID verification (`API_BASE_URL` and `API_KEY` need to be updated in the code)

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/SanityMinds/IDSafe.git
   cd IDSafe

2. Install Dependencies:
   ```bash
   pip install -r requirements.txt

3. Configure environment:
   Replace API tokens and discord token


## how to get a ZukiJourney API key?

go to: https://zukijourney.com/
