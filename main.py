import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.guilds = True
INTENTS.members = True

bot = commands.Bot(command_prefix="!", intents=INTENTS)

DATA_FILE = "scrims.json"

VALORANT_MAPS = [
    "Ascent", "Bind", "Haven", "Icebox", "Split", "Lotus", "Breeze"
]

VALORANT_RANKS = [
    "Radiant", "Immortal", "Ascendant", "Diamond", "Platinum", "Gold", "Silver", "Bronze", "Iron"
]

VALORANT_SERVERS = ["Dubai", "Bahrain"]

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"scrims": []}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands synced ({len(synced)})")
    except Exception as e:
        print(e)


class ScrimView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.format_type = None
        self.maps = None
        self.ranks = None
        self.server = None

    @discord.ui.button(label="Best of 1", style=discord.ButtonStyle.primary, custom_id="bo1")
    async def bo1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your scrim setup!", ephemeral=True)
            return
        
        self.format_type = "Best of 1"
        await self.show_map_select(interaction)

    @discord.ui.button(label="Best of 3", style=discord.ButtonStyle.primary, custom_id="bo3")
    async def bo3_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your scrim setup!", ephemeral=True)
            return
        
        self.format_type = "Best of 3"
        await self.show_map_select(interaction)

    async def show_map_select(self, interaction: discord.Interaction):
        map_options = [discord.SelectOption(label=m, value=m) for m in VALORANT_MAPS]
        map_select = discord.ui.Select(
            placeholder="Select 1–3 maps", 
            min_values=1, 
            max_values=3, 
            options=map_options,
            custom_id="map_select"
        )
        
        async def map_callback(select_interaction: discord.Interaction):
            if select_interaction.user.id != self.user_id:
                await select_interaction.response.send_message("This isn't your scrim setup!", ephemeral=True)
                return
            
            self.maps = map_select.values
            await self.show_rank_select(select_interaction)
        
        map_select.callback = map_callback
        view = discord.ui.View()
        view.add_item(map_select)
        
        await interaction.response.edit_message(
            content=f"You chose **{self.format_type}**.\nNow select maps:", 
            view=view
        )

    async def show_rank_select(self, interaction: discord.Interaction):
        rank_options = [discord.SelectOption(label=r, value=r) for r in VALORANT_RANKS]
        rank_select = discord.ui.Select(
            placeholder="Select preferred ranks", 
            min_values=1, 
            max_values=3, 
            options=rank_options,
            custom_id="rank_select"
        )
        
        async def rank_callback(rank_interaction: discord.Interaction):
            if rank_interaction.user.id != self.user_id:
                await rank_interaction.response.send_message("This isn't your scrim setup!", ephemeral=True)
                return
            
            self.ranks = rank_select.values
            await self.show_server_select(rank_interaction)
        
        rank_select.callback = rank_callback
        view = discord.ui.View()
        view.add_item(rank_select)
        
        await interaction.response.edit_message(
            content=f"Maps selected: {', '.join(self.maps)}\nNow select ranks:", 
            view=view
        )

    async def show_server_select(self, interaction: discord.Interaction):
        server_options = [discord.SelectOption(label=s, value=s) for s in VALORANT_SERVERS]
        server_select = discord.ui.Select(
            placeholder="Select preferred server", 
            min_values=1, 
            max_values=1, 
            options=server_options,
            custom_id="server_select"
        )
        
        async def server_callback(server_interaction: discord.Interaction):
            if server_interaction.user.id != self.user_id:
                await server_interaction.response.send_message("This isn't your scrim setup!", ephemeral=True)
                return
            
            self.server = server_select.values[0]
            await self.post_scrim(server_interaction)
        
        server_select.callback = server_callback
        view = discord.ui.View()
        view.add_item(server_select)
        
        await interaction.response.edit_message(
            content=f"Ranks selected: {', '.join(self.ranks)}\nNow select server:", 
            view=view
        )

    async def post_scrim(self, interaction: discord.Interaction):
        # Acknowledge the interaction first
        await interaction.response.defer(ephemeral=True)
        
        user = interaction.user
        
        # Create embed
        embed = discord.Embed(title="🎮 Valorant Scrim Request", color=0x5865F2)
        embed.add_field(name="Requester", value=f"<@{user.id}>", inline=True)
        embed.add_field(name="Format", value=self.format_type, inline=True)
        embed.add_field(name="Maps", value=", ".join(self.maps), inline=False)
        embed.add_field(name="Ranks", value=", ".join(self.ranks), inline=False)
        embed.add_field(name="Server", value=self.server, inline=True)
        embed.add_field(name="Status", value="Open", inline=True)

        # Create persistent booking view
        book_view = BookingView(user.id)
        
        # Post to channel
        scrim_message = await interaction.channel.send(embed=embed, view=book_view)
        
        # Save to file
        data = load_data()
        data["scrims"].append({
            "id": scrim_message.id,
            "guild_id": scrim_message.guild.id,
            "channel_id": scrim_message.channel.id,
            "requester_id": user.id,
            "format": self.format_type,
            "maps": self.maps,
            "ranks": self.ranks,
            "server": self.server,
            "status": "open",
            "booked_by": None
        })
        save_data(data)
        
        # Send confirmation
        await interaction.followup.send("✅ Scrim posted!", ephemeral=True)


class BookingView(discord.ui.View):
    def __init__(self, requester_id):
        super().__init__(timeout=None)
        self.requester_id = requester_id

    @discord.ui.button(label="Book Scrim", style=discord.ButtonStyle.success, custom_id="book_scrim")
    async def book_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.requester_id:
            await interaction.response.send_message("You can't book your own scrim!", ephemeral=True)
            return

        # Load data
        data = load_data()
        scrim = next((s for s in data["scrims"] if s["id"] == interaction.message.id), None)
        
        if not scrim or scrim["status"] != "open":
            await interaction.response.send_message("This scrim is already booked or invalid.", ephemeral=True)
            return

        # Update data
        scrim["status"] = "booked"
        scrim["booked_by"] = interaction.user.id
        save_data(data)

        # Update embed
        embed = interaction.message.embeds[0]
        embed.set_field_at(5, name="Status", value=f"Booked by <@{interaction.user.id}>", inline=True)
        
        # Disable button
        button.disabled = True
        button.label = "Booked"
        button.style = discord.ButtonStyle.secondary
        
        await interaction.message.edit(embed=embed, view=self)
        
        # Send confirmation
        await interaction.response.send_message(
            f"✅ Scrim booked!\n<@{self.requester_id}> vs <@{interaction.user.id}>", 
            ephemeral=False
        )

        # Try to DM both users
        try:
            requester = await bot.fetch_user(self.requester_id)
            await requester.send(f"Your scrim was booked by {interaction.user.name}.")
        except:
            pass
        
        try:
            await interaction.user.send(f"You booked a scrim with {requester.name}.")
        except:
            pass


@bot.tree.command(name="scrim", description="Create a scrim request (BO1/BO3 + maps + rank + server)")
async def scrim(interaction: discord.Interaction):
    view = ScrimView(interaction.user.id)
    await interaction.response.send_message("Choose match format:", view=view, ephemeral=True)


bot.run(TOKEN)