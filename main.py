import discord
from discord.ext import commands
import sqlite3
import os
import asyncio
import time
from dotenv import load_dotenv
from typing import Optional, List, Dict
import traceback
from datetime import datetime

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.guilds = True
INTENTS.members = True

bot = commands.Bot(command_prefix="!", intents=INTENTS)
DB_FILE = "scrims.db"

VALORANT_MAPS = ["Ascent", "Bind", "Haven", "Icebox", "Split", "Lotus", "Breeze"]
VALORANT_RANKS = ["Radiant", "Immortal", "Ascendant", "Diamond", "Platinum", "Gold", "Silver", "Bronze", "Iron"]
VALORANT_SERVERS = ["Dubai", "Bahrain"]

# -------------------- Database Setup --------------------
def init_db():
    """Initialize SQLite database with required tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create scrims table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scrims (
            id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            channel_id INTEGER NOT NULL,
            requester_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            format TEXT NOT NULL,
            maps TEXT NOT NULL,
            ranks TEXT NOT NULL,
            server TEXT NOT NULL,
            datetime TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            booked_by INTEGER,
            created_at REAL NOT NULL,
            UNIQUE(id)
        )
    ''')
    
    # Create verifications table (for tracking who verified match completion)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scrim_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            verified_at REAL NOT NULL,
            FOREIGN KEY (scrim_id) REFERENCES scrims(id),
            UNIQUE(scrim_id, user_id)
        )
    ''')
    
    # Create indexes for better performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_scrims_status ON scrims(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_scrims_requester ON scrims(requester_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_scrims_created_at ON scrims(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_verifications_scrim ON verifications(scrim_id)')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------- Database Operations --------------------
def create_scrim(scrim_data: Dict) -> bool:
    """Insert a new scrim into the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO scrims (
                id, guild_id, channel_id, requester_id, team_name,
                format, maps, ranks, server, datetime, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            scrim_data['id'],
            scrim_data.get('guild_id'),
            scrim_data['channel_id'],
            scrim_data['requester_id'],
            scrim_data['team_name'],
            scrim_data['format'],
            ','.join(scrim_data['maps']),
            ','.join(scrim_data['ranks']),
            scrim_data['server'],
            scrim_data['datetime'],
            scrim_data['status'],
            scrim_data['created_at']
        ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error creating scrim: {e}")
        traceback.print_exc()
        return False

def get_scrim_by_id(scrim_id: int) -> Optional[Dict]:
    """Retrieve a scrim by its message ID."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM scrims WHERE id = ?', (scrim_id,))
        row = cursor.fetchone()
        
        if row:
            # Get verifications for this scrim
            cursor.execute('SELECT user_id FROM verifications WHERE scrim_id = ?', (scrim_id,))
            verified_by = [v['user_id'] for v in cursor.fetchall()]
            
            scrim = dict(row)
            scrim['maps'] = scrim['maps'].split(',') if scrim['maps'] else []
            scrim['ranks'] = scrim['ranks'].split(',') if scrim['ranks'] else []
            scrim['verified_by'] = verified_by
            conn.close()
            return scrim
        
        conn.close()
        return None
    except Exception as e:
        print(f"Error getting scrim: {e}")
        traceback.print_exc()
        return None

def update_scrim_status(scrim_id: int, status: str, booked_by: Optional[int] = None) -> bool:
    """Update a scrim's status and optionally who booked it."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if booked_by is not None:
            cursor.execute(
                'UPDATE scrims SET status = ?, booked_by = ? WHERE id = ?',
                (status, booked_by, scrim_id)
            )
        else:
            cursor.execute(
                'UPDATE scrims SET status = ? WHERE id = ?',
                (status, scrim_id)
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating scrim status: {e}")
        traceback.print_exc()
        return False

def add_verification(scrim_id: int, user_id: int) -> bool:
    """Add a verification record for a scrim."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO verifications (scrim_id, user_id, verified_at)
            VALUES (?, ?, ?)
        ''', (scrim_id, user_id, time.time()))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    except Exception as e:
        print(f"Error adding verification: {e}")
        traceback.print_exc()
        return False

def get_verification_count(scrim_id: int) -> int:
    """Get the number of verifications for a scrim."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM verifications WHERE scrim_id = ?', (scrim_id,))
        count = cursor.fetchone()['count']
        
        conn.close()
        return count
    except Exception as e:
        print(f"Error getting verification count: {e}")
        traceback.print_exc()
        return 0

def user_has_verified(scrim_id: int, user_id: int) -> bool:
    """Check if a user has already verified a scrim."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT COUNT(*) as count FROM verifications WHERE scrim_id = ? AND user_id = ?',
            (scrim_id, user_id)
        )
        count = cursor.fetchone()['count']
        
        conn.close()
        return count > 0
    except Exception as e:
        print(f"Error checking verification: {e}")
        traceback.print_exc()
        return False

def get_active_scrim_for_user(user_id: int) -> Optional[Dict]:
    """Get an active (open/pending/booked) scrim for a user."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM scrims 
            WHERE requester_id = ? AND status IN ('open', 'pending', 'booked')
            ORDER BY created_at DESC
            LIMIT 1
        ''', (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            scrim = dict(row)
            scrim['maps'] = scrim['maps'].split(',') if scrim['maps'] else []
            scrim['ranks'] = scrim['ranks'].split(',') if scrim['ranks'] else []
            return scrim
        return None
    except Exception as e:
        print(f"Error getting active scrim: {e}")
        traceback.print_exc()
        return None

def get_expired_scrims(expiry_time: float) -> List[Dict]:
    """Get all open scrims that should be expired."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cutoff_time = time.time() - expiry_time
        cursor.execute('''
            SELECT * FROM scrims 
            WHERE status = 'open' AND created_at < ?
        ''', (cutoff_time,))
        
        rows = cursor.fetchall()
        conn.close()
        
        scrims = []
        for row in rows:
            scrim = dict(row)
            scrim['maps'] = scrim['maps'].split(',') if scrim['maps'] else []
            scrim['ranks'] = scrim['ranks'].split(',') if scrim['ranks'] else []
            scrims.append(scrim)
        
        return scrims
    except Exception as e:
        print(f"Error getting expired scrims: {e}")
        traceback.print_exc()
        return []

def expire_user_scrims(user_ids: List[int], exclude_id: Optional[int] = None) -> List[Dict]:
    """Expire all open scrims for given users, optionally excluding one scrim."""
    if not user_ids:
        return []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(user_ids))
        query = f'''
            SELECT * FROM scrims 
            WHERE requester_id IN ({placeholders}) AND status = 'open'
        '''
        params = list(user_ids)
        
        if exclude_id is not None:
            query += ' AND id != ?'
            params.append(exclude_id)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        expired_scrims = []
        for row in rows:
            scrim = dict(row)
            scrim['maps'] = scrim['maps'].split(',') if scrim['maps'] else []
            scrim['ranks'] = scrim['ranks'].split(',') if scrim['ranks'] else []
            expired_scrims.append(scrim)
            
            # Update status to expired
            cursor.execute('UPDATE scrims SET status = ? WHERE id = ?', ('expired', scrim['id']))
        
        conn.commit()
        conn.close()
        
        return expired_scrims
    except Exception as e:
        print(f"Error expiring user scrims: {e}")
        traceback.print_exc()
        return []

# -------------------- Helper Functions --------------------
async def safe_fetch_message(channel_id, message_id):
    """Return message or None (wrap exceptions)."""
    try:
        ch = bot.get_channel(channel_id)
        if ch is None:
            for g in bot.guilds:
                ch = g.get_channel(channel_id)
                if ch:
                    break
        if ch is None:
            return None
        return await ch.fetch_message(message_id)
    except discord.NotFound:
        print(f"Message {message_id} not found in channel {channel_id}")
        return None
    except discord.Forbidden:
        print(f"No permission to fetch message {message_id}")
        return None
    except Exception as e:
        print(f"Error fetching message: {e}")
        return None

async def update_embed_status(channel_id, message_id, status_text, remove_view=False):
    """Update embed's 'Status' field if present; otherwise append it."""
    msg = await safe_fetch_message(channel_id, message_id)
    if msg is None:
        return False

    try:
        embed = msg.embeds[0] if msg.embeds else discord.Embed(title="🎮 Valorant Scrim Request", color=0x5865F2)
    except Exception:
        embed = discord.Embed(title="🎮 Valorant Scrim Request", color=0x5865F2)

    found_idx = None
    for i, f in enumerate(embed.fields):
        if f.name.lower() == "status":
            found_idx = i
            break

    if found_idx is not None:
        try:
            embed.set_field_at(found_idx, name="Status", value=status_text, inline=True)
        except Exception:
            new_fields = []
            for i, f in enumerate(embed.fields):
                if i == found_idx:
                    new_fields.append(("Status", status_text, True))
                else:
                    new_fields.append((f.name, f.value, f.inline))
            embed.clear_fields()
            for n, v, inline in new_fields:
                embed.add_field(name=n, value=v, inline=inline)
    else:
        embed.add_field(name="Status", value=status_text, inline=True)

    try:
        if remove_view:
            await msg.edit(embed=embed, view=None)
        else:
            await msg.edit(embed=embed)
        return True
    except discord.Forbidden:
        print(f"No permission to edit message {message_id}")
        return False
    except Exception as e:
        print(f"Error updating embed: {e}")
        return False

# -------------------- Events --------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    init_db()
    print("✅ Database initialized!")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced successfully!")
    except Exception as e:
        print("Sync error:", e)
    bot.loop.create_task(expire_old_scrims())

# -------------------- Expiry Background Task --------------------
async def expire_old_scrims():
    """Background task to expire old scrims after 12 hours."""
    await bot.wait_until_ready()
    expiry_time = 12 * 60 * 60  # 12 hours
    check_interval = 600  # 10 minutes
    
    while not bot.is_closed():
        try:
            expired_scrims = get_expired_scrims(expiry_time)
            
            for scrim in expired_scrims:
                try:
                    # Update status in database
                    update_scrim_status(scrim['id'], 'expired')
                    
                    # Update embed
                    await update_embed_status(
                        scrim['channel_id'], 
                        scrim['id'], 
                        "Expired ⏰", 
                        remove_view=True
                    )
                    
                    # Try to delete message
                    msg = await safe_fetch_message(scrim['channel_id'], scrim['id'])
                    if msg:
                        try:
                            await asyncio.sleep(1)
                            await msg.delete()
                        except Exception as e:
                            print(f"Could not delete expired message: {e}")
                    
                    # DM requester
                    try:
                        requester = await bot.fetch_user(scrim['requester_id'])
                        if requester:
                            await requester.send("⏰ Your scrim request has expired after 12 hours.")
                    except Exception as e:
                        print(f"Could not DM user about expiry: {e}")
                        
                except Exception as e:
                    print(f"Error processing expired scrim {scrim.get('id')}: {e}")
                    continue
        except Exception as e:
            print(f"Error in expire_old_scrims task: {e}")
            traceback.print_exc()
        
        await asyncio.sleep(check_interval)

# -------------------- Scrim Creation UI --------------------
class ScrimView(discord.ui.View):
    def __init__(self, user_id, team_name, match_datetime):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.team_name = team_name
        self.match_datetime = match_datetime
        self.format_type = None
        self.maps = []
        self.ranks = []
        self.server = None

    @discord.ui.button(label="Best of 1", style=discord.ButtonStyle.primary)
    async def bo1(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your setup!", ephemeral=True)
        self.format_type = "Best of 1"
        await self._show_map_select(interaction)

    @discord.ui.button(label="Best of 3", style=discord.ButtonStyle.primary)
    async def bo3(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your setup!", ephemeral=True)
        self.format_type = "Best of 3"
        await self._show_map_select(interaction)

    async def _show_map_select(self, interaction: discord.Interaction):
        options = [discord.SelectOption(label=m, value=m) for m in VALORANT_MAPS]
        max_maps = 1 if self.format_type == "Best of 1" else 3
        select = discord.ui.Select(placeholder=f"Select maps ({max_maps} max)", min_values=1, max_values=max_maps, options=options)

        async def callback(i: discord.Interaction):
            if i.user.id != self.user_id:
                return await i.response.send_message("Not your setup!", ephemeral=True)
            self.maps = select.values
            await self._show_rank_select(i)

        select.callback = callback
        v = discord.ui.View()
        v.add_item(select)
        await interaction.response.edit_message(content=f"Format: **{self.format_type}**\nSelect maps:", view=v)

    async def _show_rank_select(self, interaction: discord.Interaction):
        options = [discord.SelectOption(label=r, value=r) for r in VALORANT_RANKS]
        select = discord.ui.Select(placeholder="Select ranks (max 3)", min_values=1, max_values=3, options=options)

        async def callback(i: discord.Interaction):
            if i.user.id != self.user_id:
                return await i.response.send_message("Not your setup!", ephemeral=True)
            self.ranks = select.values
            await self._show_server_select(i)

        select.callback = callback
        v = discord.ui.View()
        v.add_item(select)
        await interaction.response.edit_message(content=f"Maps: {', '.join(self.maps)}\nSelect ranks:", view=v)

    async def _show_server_select(self, interaction: discord.Interaction):
        options = [discord.SelectOption(label=s, value=s) for s in VALORANT_SERVERS]
        select = discord.ui.Select(placeholder="Select server", min_values=1, max_values=1, options=options)

        async def callback(i: discord.Interaction):
            if i.user.id != self.user_id:
                return await i.response.send_message("Not your setup!", ephemeral=True)
            self.server = select.values[0]
            await self._post_scrim(i)

        select.callback = callback
        v = discord.ui.View()
        v.add_item(select)
        await interaction.response.edit_message(content=f"Ranks: {', '.join(self.ranks)}\nSelect server:", view=v)

    async def _post_scrim(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(title="🎮 Valorant Scrim Request", color=0x5865F2)
        embed.add_field(name="Requester", value=f"<@{interaction.user.id}>", inline=True)
        embed.add_field(name="Team", value=self.team_name, inline=True)
        embed.add_field(name="Format", value=self.format_type, inline=True)
        embed.add_field(name="Maps", value=", ".join(self.maps) or "N/A", inline=False)
        embed.add_field(name="Ranks", value=", ".join(self.ranks) or "N/A", inline=False)
        embed.add_field(name="Server", value=self.server or "N/A", inline=True)
        embed.add_field(name="Date/Time", value=self.match_datetime or "N/A", inline=True)
        embed.add_field(name="Status", value="Open", inline=True)

        view = BookingView(interaction.user.id)
        sent = await interaction.channel.send(embed=embed, view=view)

        scrim_data = {
            "id": sent.id,
            "guild_id": sent.guild.id if sent.guild else None,
            "channel_id": sent.channel.id,
            "requester_id": interaction.user.id,
            "team_name": self.team_name,
            "format": self.format_type,
            "maps": self.maps,
            "ranks": self.ranks,
            "server": self.server,
            "datetime": self.match_datetime,
            "status": "open",
            "created_at": time.time()
        }
        
        success = create_scrim(scrim_data)
        if success:
            await interaction.followup.send("✅ Scrim posted!", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Scrim posted but there was an issue saving to database.", ephemeral=True)

# -------------------- Booking View --------------------
class BookingView(discord.ui.View):
    def __init__(self, requester_id):
        super().__init__(timeout=None)
        self.requester_id = requester_id

    @discord.ui.button(label="Book Scrim", style=discord.ButtonStyle.success)
    async def book_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.requester_id:
            return await interaction.response.send_message("You can't book your own scrim!", ephemeral=True)

        scrim = get_scrim_by_id(interaction.message.id)
        if not scrim:
            return await interaction.response.send_message("Scrim not found in database.", ephemeral=True)
        
        if scrim['status'] != "open":
            return await interaction.response.send_message("This scrim is no longer available.", ephemeral=True)

        try:
            requester = await bot.fetch_user(self.requester_id)
        except Exception as e:
            print(f"Could not fetch requester: {e}")
            return await interaction.response.send_message("Could not find scrim creator.", ephemeral=True)

        challenger = interaction.user

        # Update to pending immediately
        update_scrim_status(scrim['id'], 'pending', challenger.id)

        await interaction.response.send_message("✅ Booking request sent. Waiting for Ready Check in DMs...", ephemeral=True)

        # Start ready check in background to avoid blocking
        bot.loop.create_task(self._ready_check(requester, challenger, interaction.message, scrim))

    async def _ready_check(self, requester_user, challenger_user, channel_msg, scrim):
        """Send DM ready check to both users."""
        try:
            dm1 = await requester_user.send(
                f"⚔️ Ready Check: {challenger_user.name} wants to book your scrim at **{scrim['datetime']}**. "
                f"React ✅ within 30 minutes to confirm."
            )
            await dm1.add_reaction("✅")
        except Exception as e:
            print(f"Could not DM requester: {e}")
            dm1 = None

        try:
            dm2 = await challenger_user.send(
                f"⚔️ Ready Check: You requested to book {requester_user.name}'s scrim at **{scrim['datetime']}**. "
                f"React ✅ within 30 minutes to confirm."
            )
            await dm2.add_reaction("✅")
        except Exception as e:
            print(f"Could not DM challenger: {e}")
            dm2 = None

        if not dm1 or not dm2:
            # Revert to open if DMs failed
            update_scrim_status(scrim['id'], 'open', None)
            try:
                if dm1:
                    await requester_user.send("⚠️ Ready check failed — could not DM the other party.")
                if dm2:
                    await challenger_user.send("⚠️ Ready check failed — could not DM the other party.")
            except Exception:
                pass
            return

        dm_ids = {dm1.id, dm2.id}
        confirmed = set()
        timeout = 1800.0  # 30 minutes

        def check(reaction, user):
            try:
                return (
                    reaction and 
                    reaction.message and
                    reaction.message.id in dm_ids and
                    str(reaction.emoji) == "✅" and
                    user.id in {requester_user.id, challenger_user.id}
                )
            except Exception:
                return False

        try:
            while len(confirmed) < 2:
                reaction, user = await bot.wait_for("reaction_add", timeout=timeout, check=check)
                confirmed.add(user.id)
        except asyncio.TimeoutError:
            # Timeout - revert to open
            update_scrim_status(scrim['id'], 'open', None)
            try:
                await requester_user.send("❌ Ready check timed out — not all parties confirmed within 30 minutes.")
            except Exception:
                pass
            try:
                await challenger_user.send("❌ Ready check timed out — not all parties confirmed within 30 minutes.")
            except Exception:
                pass
            return

        # Both confirmed - expire other open scrims and mark this as booked
        expired_scrims = expire_user_scrims(
            [requester_user.id, challenger_user.id],
            exclude_id=scrim['id']
        )
        
        for s in expired_scrims:
            try:
                await update_embed_status(s['channel_id'], s['id'], "Expired ⏰", remove_view=True)
                try:
                    msg = await safe_fetch_message(s['channel_id'], s['id'])
                    if msg:
                        await asyncio.sleep(0.5)
                        await msg.delete()
                except Exception:
                    pass
            except Exception as e:
                print(f"Error expiring scrim {s['id']}: {e}")
                continue

        # Mark as booked
        update_scrim_status(scrim['id'], 'booked', challenger_user.id)

        # Update the channel message
        await update_embed_status(channel_msg.channel.id, channel_msg.id, f"Booked by <@{challenger_user.id}>")
        
        try:
            await channel_msg.edit(view=MatchVerificationView(
                scrim_id=scrim['id'], 
                requester_id=requester_user.id, 
                challenger_id=challenger_user.id
            ))
        except Exception as e:
            print(f"Error updating message view: {e}")

# -------------------- Match Verification --------------------
class MatchVerificationView(discord.ui.View):
    def __init__(self, scrim_id, requester_id, challenger_id):
        super().__init__(timeout=None)
        self.scrim_id = scrim_id
        self.requester_id = requester_id
        self.challenger_id = challenger_id

    @discord.ui.button(label="✅ Match Completed", style=discord.ButtonStyle.success)
    async def match_completed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in {self.requester_id, self.challenger_id}:
            return await interaction.response.send_message("You are not part of this match!", ephemeral=True)

        scrim = get_scrim_by_id(self.scrim_id)
        if not scrim:
            return await interaction.response.send_message("Scrim record not found.", ephemeral=True)

        if scrim['status'] != "booked":
            return await interaction.response.send_message("This match is not in booked status.", ephemeral=True)

        if user_has_verified(self.scrim_id, interaction.user.id):
            return await interaction.response.send_message("You already confirmed.", ephemeral=True)

        # Add verification
        added = add_verification(self.scrim_id, interaction.user.id)
        if not added:
            return await interaction.response.send_message("Could not record verification.", ephemeral=True)

        verification_count = get_verification_count(self.scrim_id)

        if verification_count >= 2:
            # Both verified - mark as played
            update_scrim_status(self.scrim_id, 'played')

            await update_embed_status(
                interaction.message.channel.id, 
                interaction.message.id, 
                "Played ✅", 
                remove_view=True
            )

            # Expire other open scrims for both players
            expired_scrims = expire_user_scrims(
                [scrim['requester_id'], scrim['booked_by']],
                exclude_id=self.scrim_id
            )
            
            for s in expired_scrims:
                try:
                    await update_embed_status(s['channel_id'], s['id'], "Expired ⏰", remove_view=True)
                    msg = await safe_fetch_message(s['channel_id'], s['id'])
                    if msg:
                        try:
                            await asyncio.sleep(0.5)
                            await msg.delete()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"Error expiring scrim {s['id']}: {e}")
                    continue

            await interaction.response.send_message("✅ Match verified by both teams! Status updated to Played.", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Your confirmation has been recorded. Waiting for the other team.", ephemeral=True)

# -------------------- Slash Commands --------------------
@bot.tree.command(name="scrim", description="Create a Valorant scrim request")
async def create_scrim_cmd(interaction: discord.Interaction):
    user_id = interaction.user.id
    active = get_active_scrim_for_user(user_id)
    
    if active:
        return await interaction.response.send_message(
            f"⚠️ You already have an active scrim request (Status: {active['status']}). "
            "Cancel or wait for it to finish before creating a new one.", 
            ephemeral=True
        )

    modal = ScrimModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="cancel_scrim", description="Cancel your active scrim request")
async def cancel_scrim(interaction: discord.Interaction):
    user_id = interaction.user.id
    active = get_active_scrim_for_user(user_id)
    
    if not active:
        return await interaction.response.send_message("❌ You have no active scrim to cancel.", ephemeral=True)
    
    if active['status'] != 'open':
        return await interaction.response.send_message(
            f"❌ Your scrim is currently {active['status']} and cannot be cancelled.", 
            ephemeral=True
        )

    # Update status to cancelled
    update_scrim_status(active['id'], 'cancelled')

    # Update embed
    await update_embed_status(active['channel_id'], active['id'], "Cancelled ❌", remove_view=True)
    
    # Try to delete the message
    msg = await safe_fetch_message(active['channel_id'], active['id'])
    if msg:
        try:
            await asyncio.sleep(0.3)
            await msg.delete()
        except Exception as e:
            print(f"Could not delete cancelled message: {e}")

    await interaction.response.send_message("✅ Your scrim has been cancelled.", ephemeral=True)

@bot.tree.command(name="my_scrim", description="View your current active scrim")
async def my_scrim(interaction: discord.Interaction):
    user_id = interaction.user.id
    active = get_active_scrim_for_user(user_id)
    
    if not active:
        return await interaction.response.send_message("❌ You don't have any active scrims.", ephemeral=True)
    
    embed = discord.Embed(title="Your Active Scrim", color=0x5865F2)
    embed.add_field(name="Team", value=active['team_name'], inline=True)
    embed.add_field(name="Format", value=active['format'], inline=True)
    embed.add_field(name="Status", value=active['status'].capitalize(), inline=True)
    embed.add_field(name="Maps", value=", ".join(active['maps']), inline=False)
    embed.add_field(name="Ranks", value=", ".join(active['ranks']), inline=False)
    embed.add_field(name="Server", value=active['server'], inline=True)
    embed.add_field(name="Date/Time", value=active['datetime'], inline=True)
    
    if active.get('booked_by'):
        embed.add_field(name="Booked By", value=f"<@{active['booked_by']}>", inline=True)
    
    created_time = int(active['created_at'])
    embed.set_footer(text=f"Created")
    embed.timestamp = datetime.fromtimestamp(created_time)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -------------------- Modal --------------------
class ScrimModal(discord.ui.Modal, title="Create Scrim"):
    team_name = discord.ui.TextInput(
        label="Team Name", 
        required=True,
        max_length=50,
        placeholder="Enter your team name"
    )
    match_datetime = discord.ui.TextInput(
        label="Match Time", 
        required=True,
        max_length=100,
        placeholder="e.g. Today 9:00 PM or Tomorrow 3:00 PM"
    )

    async def on_submit(self, interaction: discord.Interaction):
        view = ScrimView(interaction.user.id, str(self.team_name), str(self.match_datetime))
        await interaction.response.send_message("Choose format:", view=view, ephemeral=True)

# -------------------- Error Handlers --------------------
@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Command error: {error}")
    traceback.print_exc()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    """Handle slash command errors."""
    if interaction.response.is_done():
        await interaction.followup.send("❌ An error occurred while processing your command.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred while processing your command.", ephemeral=True)
    print(f"App command error: {error}")
    traceback.print_exc()

# -------------------- Run --------------------
if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: DISCORD_TOKEN not found in environment variables!")
        print("Please create a .env file with DISCORD_TOKEN=your_token_here")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"❌ Error running bot: {e}")
            traceback.print_exc()