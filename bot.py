import discord
import requests
import datetime
import os
import logging
import sqlite3
import random
import string
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

# Initialize the API base URL and key
API_BASE_URL = "https://api.zukijourney.com/v1"
API_KEY = "ZUKI_JOURNEY_TOKEN"

conn = sqlite3.connect('verification_settings.db')
c = conn.cursor()

try:
    c.execute("ALTER TABLE human_verification ADD COLUMN country TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    c.execute("ALTER TABLE settings ADD COLUMN human_verification_enabled BOOLEAN DEFAULT 1")  # Default is 'True'
    conn.commit()
except sqlite3.OperationalError:
    pass

c.execute('''CREATE TABLE IF NOT EXISTS human_verification (
    case_id TEXT PRIMARY KEY, 
    user_id INTEGER, 
    username TEXT, 
    guild_id INTEGER, 
    guild_name TEXT, 
    image_url TEXT, 
    country TEXT, 
    requested_at TEXT)''')
conn.commit()

c.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        guild_id INTEGER PRIMARY KEY, 
        verification_channel_id INTEGER, 
        verified_role_id INTEGER, 
        human_verification_enabled INTEGER DEFAULT 1 -- Default is 1 (enabled)
    )
''')
conn.commit()

logging.basicConfig(
    filename='verification_logs.log',  # Log file where API requests and responses will be stored
    level=logging.INFO,  # Log level set to INFO to capture necessary details
    format='%(asctime)s - %(levelname)s - %(message)s'
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Staff review channel ID (replace this with your actual staff review channel ID)
STAFF_REVIEW_CHANNEL_ID = 1128232339516960799  # Example channel ID for staff review
AUTHORIZED_STAFF_IDS = [974368593615659098, 987654321098765432]  # Replace with actual staff member IDs

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}. Commands have been synced.")
    logging.info(f"Logged in as {bot.user}. Commands have been synced.")


def generate_case_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def call_api(id_image_url, selfie_image_url, country):
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }

    current_date = datetime.datetime.now().strftime("%d/%m/%y")

    data = {
        "model": "claude-3-opus",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Analyze this ID issued in {country} as of the current date {current_date}. Please respond in the following format without deviating from it: \n\n"
                                              "the ID appears fake: YES/NO\n"
                                              "the ID was captured with a phone camera: YES/NO (If YES, explain why you believe it was captured with a phone camera)\n"
                                              "The ID expiration date is: (state expiration date)\n"
                                              "The ID shows the user aged over 18?: YES/NO\n"
                                              "Face matches the ID?: YES/NO\n\n"
                                              "Only provide the information asked. Do not include your opinion on whether the verification should be denied."},
                    {
                        "type": "image_url",
                        "image_url": id_image_url,
                    },
                    {
                        "type": "image_url",
                        "image_url": selfie_image_url,
                    }
                ],
            }
        ],
        "max_tokens": 300,
    }

    logging.info(f"API Request: {data}")

    response = requests.post(f"{API_BASE_URL}/chat/completions", headers=headers, json=data)

    logging.info(f"API Response: {response.json()}")

    return response.json()

class ConfirmView(View):
    def __init__(self, id_attachment, selfie_attachment, case_id, user_id, username, guild_id, guild_name, id_image_url, selfie_image_url, country):
        super().__init__(timeout=60)
        self.id_attachment = id_attachment
        self.selfie_attachment = selfie_attachment
        self.case_id = case_id
        self.user_id = user_id
        self.username = username
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.id_image_url = id_image_url
        self.selfie_image_url = selfie_image_url
        self.country = country

    @discord.ui.button(label="✅ Yes", style=discord.ButtonStyle.green, emoji="✅")
    async def yes_button(self, interaction: discord.Interaction, button: Button):
        requested_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO human_verification (case_id, user_id, username, guild_id, guild_name, image_url, country, requested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (self.case_id, self.user_id, self.username, self.guild_id, self.guild_name, self.id_image_url, self.country, requested_at))
        conn.commit()

        staff_channel = bot.get_channel(STAFF_REVIEW_CHANNEL_ID)
        staff_embed = discord.Embed(
            title="📝 New Human Verification Request",
            description="A user has submitted a request for manual verification.",
            color=discord.Color.blue()
        )
        staff_embed.add_field(name="Case ID", value=self.case_id, inline=False)
        staff_embed.add_field(name="User", value=f"{self.username} (ID: {self.user_id})", inline=False)
        staff_embed.add_field(name="Server", value=f"{self.guild_name} (ID: {self.guild_id})", inline=False)
        staff_embed.add_field(name="Country", value=self.country, inline=False)
        staff_embed.add_field(name="Requested At", value=requested_at, inline=False)
        staff_embed.add_field(name="ID Image", value=f"[Click to view ID]({self.id_image_url})", inline=False)
        staff_embed.add_field(name="Selfie Image", value=f"[Click to view Selfie]({self.selfie_image_url})", inline=False)
        staff_embed.set_footer(text="Review and make a decision on this request.")

        await staff_channel.send(embed=staff_embed)

        await interaction.response.send_message(f"Your human verification request has been submitted. Case ID: {self.case_id}.", ephemeral=True)

    @discord.ui.button(label="❌ No", style=discord.ButtonStyle.red, emoji="❌")
    async def no_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("You have canceled the human verification request.", ephemeral=True)

@bot.tree.command(name="human_verify", description="Request human verification for your ID")
@app_commands.describe(country="Country where the ID was issued", id_attachment="Image of your ID", selfie_attachment="A selfie image for face verification")
async def human_verify(interaction: discord.Interaction, country: str, id_attachment: discord.Attachment, selfie_attachment: discord.Attachment):
    try:
        c.execute("SELECT verification_channel_id, human_verification_enabled FROM settings WHERE guild_id=?", (interaction.guild.id,))
        result = c.fetchone()

        if not result:
            embed = discord.Embed(
                title="⚠️ Setup Not Complete",
                description="Verification has not been set up for this server. Please ask an admin to run `/setup` first.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        verification_channel_id, human_verification_enabled = result

        if not human_verification_enabled:
            embed = discord.Embed(
                title="⚠️ Human Verification Disabled",
                description="Human verification is disabled for this server. Please contact an admin if you believe this is incorrect.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if interaction.channel.id != verification_channel_id:
            embed = discord.Embed(
                title="⚠️ Wrong Channel",
                description=f"Please use the designated verification channel <#{verification_channel_id}>.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        id_image_url = id_attachment.url
        selfie_image_url = selfie_attachment.url

        logging.info(f"Processing verification for {interaction.user.name} with ID image URL: {id_image_url} and Selfie image URL: {selfie_image_url}")

        case_id = generate_case_id()
        guild_id = interaction.guild.id
        guild_name = interaction.guild.name
        user_id = interaction.user.id
        username = interaction.user.name

        embed = discord.Embed(
            title="👤 Human Verification Request",
            description="By clicking **Yes**, you agree that your document will be stored for up to **72 hours** while the bot development team manually verifies your ID.\n\nDo you wish to proceed?",
            color=discord.Color.orange()
        )
        embed.add_field(name="Country", value=country, inline=True)
        embed.add_field(name="User", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Please respond within 60 seconds.")

        view = ConfirmView(id_attachment, selfie_attachment, case_id, user_id, username, guild_id, guild_name, id_image_url, selfie_image_url, country)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        error_embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred during the verification request: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="handle_case", description="Handle a human verification case (Staff Only)")
@app_commands.describe(case_id="The ID of the case to handle", decision="Accept or deny the case")
@app_commands.choices(decision=[
    app_commands.Choice(name="Accept", value="accept"),
    app_commands.Choice(name="Deny", value="deny")
])
async def handle_case(interaction: discord.Interaction, case_id: str, decision: app_commands.Choice[str]):
    if interaction.user.id not in AUTHORIZED_STAFF_IDS:
        embed = discord.Embed(
            title="⚠️ Access Denied",
            description="You are not authorized to use this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    c.execute("SELECT user_id, username, guild_id, guild_name FROM human_verification WHERE case_id=?", (case_id,))
    result = c.fetchone()

    if not result:
        embed = discord.Embed(
            title="❌ Invalid Case ID",
            description="The provided case ID is not valid. Please check and try again.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    user_id, username, guild_id, guild_name = result

    user = await bot.fetch_user(user_id)

    await interaction.response.defer(ephemeral=True)

    if decision.value == "accept":
        message = f"Hello {user.mention}! You recently requested human verification inside of **{guild_name}**, and the development team of this bot has **accepted** your verification. If you have any concerns, feel free to contact admin@bytelabs.site."

        c.execute("SELECT verified_role_id FROM settings WHERE guild_id=?", (guild_id,))
        verified_role_id = c.fetchone()

        if verified_role_id:
            role = interaction.guild.get_role(verified_role_id[0])

            if not role:
                embed = discord.Embed(
                    title="⚠️ Role Not Found",
                    description=f"Could not find the verified role with ID {verified_role_id[0]} in guild {guild_name}.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                member = await interaction.guild.fetch_member(user_id)
            except discord.NotFound:
                embed = discord.Embed(
                    title="⚠️ Member Not Found",
                    description=f"Could not find the member with ID {user_id} in guild {guild_name}.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if not interaction.guild.me.guild_permissions.manage_roles:
                embed = discord.Embed(
                    title="⚠️ Insufficient Permissions",
                    description="The bot does not have permission to manage roles in this guild.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await member.add_roles(role)
                embed = discord.Embed(
                    title="✅ Verification Accepted",
                    description=f"User {member.name} has been successfully verified and assigned the role.",
                    color=discord.Color.green()
                )
                logging.info(f"Assigned verified role to {member.name} in {guild_name}")
                await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.Forbidden:
                embed = discord.Embed(
                    title="⚠️ Role Assignment Failed",
                    description="The bot does not have permission to assign roles in this guild.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.HTTPException as e:
                embed = discord.Embed(
                    title="⚠️ Error",
                    description=f"Failed to assign the role due to an error: {e}",
                    color=discord.Color.red()
                )
                logging.error(f"Failed to assign role to {member.name} in {guild_name} due to an error: {e}")
                await interaction.followup.send(embed=embed, ephemeral=True)

    elif decision.value == "deny":
        message = f"Hello {user.mention}! You recently requested human verification inside of **{guild_name}**, and the development team of this bot has **denied** your verification. If you feel this is incorrect, you can contact us at admin@bytelabs.site."
        embed = discord.Embed(
            title="❌ Verification Denied",
            description=f"User {username}'s verification request has been denied.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    try:
        await user.send(message)
    except discord.Forbidden:
        logging.error(f"Could not send DM to {user.name}.")

    c.execute("DELETE FROM human_verification WHERE case_id=?", (case_id,))
    conn.commit()

    embed_final = discord.Embed(
        title="✅ Case Handled",
        description=f"Case {case_id} has been handled and the user has been notified.",
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed_final, ephemeral=False)


@bot.tree.command(name="verify", description="Verify your age with an ID and selfie")
@app_commands.describe(country="Country where the ID was issued", id_attachment="Image of your ID", selfie_attachment="Your selfie picture")
async def verify(interaction: discord.Interaction, country: str, id_attachment: discord.Attachment, selfie_attachment: discord.Attachment):
    try:
        c.execute("SELECT verification_channel_id, verified_role_id FROM settings WHERE guild_id=?", (interaction.guild.id,))
        result = c.fetchone()

        if not result:
            embed = discord.Embed(
                title="⚠️ Setup Not Complete",
                description="Verification has not been set up for this server. Please ask an admin to run `/setup` first.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        verification_channel_id, verified_role_id = result

        if interaction.channel.id != verification_channel_id:
            embed = discord.Embed(
                title="⚠️ Wrong Channel",
                description="Please use the designated verification channel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        id_image_url = id_attachment.url
        selfie_image_url = selfie_attachment.url
        logging.info(f"Processing verification for {interaction.user.name} with ID URL: {id_image_url} and selfie URL: {selfie_image_url}")

        response = call_api(id_image_url, selfie_image_url, country)
        logging.info(f"Received AI Response: {response}")

        response_text = response['choices'][0]['message']['content']
        logging.info(f"AI Response Text: {response_text}")

        lines = response_text.splitlines()
        is_fake = "YES" in lines[0]
        is_phone_camera = "YES" in lines[1]
        expiration_text = lines[2]
        is_over_18 = "YES" in lines[3]
        face_match = "YES" in lines[4]

        import re
        match = re.search(r'(\d{2}-\d{2}-\d{4})', expiration_text)
        if match:
            expiration_date_str = match.group(1)
            expiration_date = datetime.datetime.strptime(expiration_date_str, "%d-%m-%Y").date()
            current_date = datetime.date.today()

            is_in_date = expiration_date >= current_date
            logging.info(f"ID is valid, expires on {expiration_date}.")
        else:
            is_in_date = False
            logging.info(f"No valid expiration date found in the text: {expiration_text}")

        result_embed = discord.Embed(
            title="ID Verification Results",
            color=discord.Color.green() if not is_fake and is_in_date and is_over_18 and face_match else discord.Color.red(),
        )
        result_embed.add_field(name="ID Fake?", value="❌ Yes" if is_fake else "✅ No", inline=True)
        result_embed.add_field(name="Captured by Phone?", value="✅ Yes" if is_phone_camera else "❌ No", inline=True)
        result_embed.add_field(name="ID In Date?", value="❌ No" if not is_in_date else "✅ Yes", inline=True)
        result_embed.add_field(name="Over 18?", value="❌ No" if not is_over_18 else "✅ Yes", inline=True)
        result_embed.add_field(name="Face Match?", value="❌ No" if not face_match else "✅ Yes", inline=True)
        result_embed.set_footer(text=f"Verification request by {interaction.user.display_name}")

        logging.info(f"Attempting to send follow-up embed for {interaction.user.name}")

        await interaction.followup.send(embed=result_embed)

        if not is_fake and is_in_date and is_over_18 and face_match:
            role = interaction.guild.get_role(verified_role_id)

            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except discord.NotFound:
                embed = discord.Embed(
                    title="⚠️ Member Not Found",
                    description=f"Could not find the member {interaction.user.mention} in this guild.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if not role:
                embed = discord.Embed(
                    title="⚠️ Role Not Found",
                    description=f"Could not find the verified role with ID {verified_role_id} in this guild.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            bot_member = interaction.guild.me
            if not bot_member.guild_permissions.manage_roles:
                embed = discord.Embed(
                    title="⚠️ Insufficient Permissions",
                    description="The bot does not have permission to manage roles in this guild.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if bot_member.top_role <= role:
                embed = discord.Embed(
                    title="⚠️ Role Hierarchy Issue",
                    description="I cannot assign the specified role because my role is not high enough in the role hierarchy. Please adjust my role position above the verified role.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await member.add_roles(role)
                logging.info(f"Assigned verified role to {member.name} in {interaction.guild.name}")
                success_embed = discord.Embed(
                    title="✅ Verification Successful",
                    description=f"ID and face verified successfully! {interaction.user.mention} has been assigned the verified role.",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=success_embed)
            except discord.Forbidden:
                embed = discord.Embed(
                    title="⚠️ Role Assignment Failed",
                    description="The bot does not have permission to assign roles in this guild.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.HTTPException as e:
                embed = discord.Embed(
                    title="⚠️ Error",
                    description=f"Failed to assign the role due to an error: {e}",
                    color=discord.Color.red()
                )
                logging.error(f"Failed to assign role to {member.name} in {interaction.guild.name} due to an error: {e}")
                await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        error_embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred during verification: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="setup", description="Setup the verification channel and role (Admin Only, can only be used once)")
@app_commands.describe(verification_channel="The channel where verification will take place", verified_role="The role to assign upon successful verification", enable_human_verification="Enable human verification? Default is Yes.")
async def setup(interaction: discord.Interaction, verification_channel: discord.TextChannel, verified_role: discord.Role, enable_human_verification: bool = True):
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="⚠️ Access Denied",
            description="You must be an admin to run this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id

    c.execute("SELECT * FROM settings WHERE guild_id=?", (guild_id,))
    if c.fetchone():
        embed = discord.Embed(
            title="⚠️ Setup Already Completed",
            description="The setup has already been completed for this server. Please use the `/settings` command to modify the current configuration.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    bot_member = interaction.guild.get_member(bot.user.id)
    if not bot_member.guild_permissions.manage_roles:
        embed = discord.Embed(
            title="⚠️ Insufficient Permissions",
            description="I do not have permission to manage roles. Please ensure I have the `Manage Roles` permission.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if bot_member.top_role <= verified_role:
        embed = discord.Embed(
            title="⚠️ Role Hierarchy Issue",
            description="I cannot assign the specified role because my role is not high enough in the role hierarchy. Please adjust my role position above the verified role.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not verification_channel.permissions_for(bot_member).send_messages:
        embed = discord.Embed(
            title="⚠️ Insufficient Permissions",
            description=f"I cannot send messages in {verification_channel.mention}. Please ensure I have the `Send Messages` permission in that channel.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    c.execute("INSERT INTO settings (guild_id, verification_channel_id, verified_role_id, human_verification_enabled) VALUES (?, ?, ?, ?)",
              (guild_id, verification_channel.id, verified_role.id, enable_human_verification))
    conn.commit()

    embed = discord.Embed(
        title="✅ Setup Complete",
        description=f"Verification has been set up!\n\n"
                    f"**Verification Channel**: {verification_channel.mention}\n"
                    f"**Verified Role**: {verified_role.mention}\n"
                    f"**Human Verification Enabled**: {'Yes' if enable_human_verification else 'No'}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="settings", description="View or update the current verification settings (Admin Only)")
@app_commands.describe(verification_channel="Change the verification channel (optional)", verified_role="Change the verified role (optional)", enable_human_verification="Enable or disable human verification (optional)")
async def settings(interaction: discord.Interaction, verification_channel: discord.TextChannel = None, verified_role: discord.Role = None, enable_human_verification: bool = None):
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="⚠️ Access Denied",
            description="You must be an admin to run this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild.id

    c.execute("SELECT verification_channel_id, verified_role_id, human_verification_enabled FROM settings WHERE guild_id=?", (guild_id,))
    result = c.fetchone()

    if not result:
        embed = discord.Embed(
            title="⚠️ No Settings Found",
            description="No verification settings have been configured yet. Please run `/setup` first.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    current_channel_id, current_role_id, current_human_verification = result

    if verification_channel or verified_role or enable_human_verification is not None:
        new_channel_id = verification_channel.id if verification_channel else current_channel_id
        new_role_id = verified_role.id if verified_role else current_role_id
        new_human_verification = enable_human_verification if enable_human_verification is not None else current_human_verification

        bot_member = interaction.guild.get_member(bot.user.id)

        if not bot_member.guild_permissions.manage_roles:
            embed = discord.Embed(
                title="⚠️ Insufficient Permissions",
                description="I do not have permission to manage roles. Please ensure I have the `Manage Roles` permission.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if verified_role and bot_member.top_role <= verified_role:
            embed = discord.Embed(
                title="⚠️ Role Hierarchy Issue",
                description="I cannot assign the specified role because my role is not high enough in the role hierarchy. Please adjust my role position above the verified role.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if verification_channel and not verification_channel.permissions_for(bot_member).send_messages:
            embed = discord.Embed(
                title="⚠️ Insufficient Permissions",
                description=f"I cannot send messages in {verification_channel.mention}. Please ensure I have the `Send Messages` permission in that channel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        c.execute("UPDATE settings SET verification_channel_id=?, verified_role_id=?, human_verification_enabled=? WHERE guild_id=?",
                  (new_channel_id, new_role_id, new_human_verification, guild_id))
        conn.commit()

        embed = discord.Embed(
            title="✅ Settings Updated",
            description=f"Settings have been updated!\n\n"
                        f"**Verification Channel**: {verification_channel.mention if verification_channel else f'<#{current_channel_id}>'}\n"
                        f"**Verified Role**: {verified_role.mention if verified_role else f'<@&{current_role_id}>'}\n"
                        f"**Human Verification Enabled**: {'Yes' if new_human_verification else 'No'}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    else:
        embed = discord.Embed(
            title="⚙️ Current Settings",
            description=f"**Verification Channel**: <#{current_channel_id}>\n"
                        f"**Verified Role**: <@&{current_role_id}>\n"
                        f"**Human Verification Enabled**: {'Yes' if current_human_verification else 'No'}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

bot.run('DISCORD_TOKEN')
