import discord
from discord import app_commands
from discord.ext import commands, tasks

import requests
import json
import pickle
import codecs
import secrets
import string
import asyncio
import datetime
from configparser import ConfigParser

configuration = ConfigParser()
configuration.read("config.ini")

MSGS = ConfigParser()
MSGS.read("msgs.ini")

# Set up using info from config
# todo, could make this automated for new servers
guild_ids = [int(configuration.get("discord_ids", "guild"))] # Put your server ID in this array. Guilds are servers.
bot_token = configuration.get("tokens", "bottoken")
channel_ids = {"modchannel":int(configuration.get("discord_ids", "modchannel")),
    "botchannel": int(configuration.get("discord_ids", "botchannel")),
    "modchat": [int(configuration.get("discord_ids", "modchat"))],
    "webhooks": int(configuration.get("discord_ids", "webhooks"))}
GAS_URL = configuration.get("tokens", "gasurl")
GAS_TOKEN = configuration.get("tokens", "gastoken")
MEMBER_ROLE_ID = int(configuration.get("discord_ids", "memberrole"))
SERVER_OWNER_ID= int(configuration.get("discord_ids", "serverrole"))

# todo, continue separating out user and mod facing message content from this code
helpcontent = MSGS.get("msgs", "welcomemsg")
helpcontent = codecs.decode(helpcontent, "unicode-escape")
MSG_on_modchat_open = MSGS.get("msgs", "MSG_on_modchat_open")
SERVER_NAME = MSGS.get("msgs","SERVER_NAME")

#Don't restart your bot more than twice a minute or you will be rate-limited
class aclient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members=True
        intents.message_content=True
        super().__init__(intents=intents)
        self.synced = False
        self.added = False

client = aclient() # set up the discord client
tree = app_commands.CommandTree(client)
client.botmemory = dict()

# debug tool to delete all messages in the channels specified
async def delete_debug_messages(id_list):
    for channel_id in id_list:
        channel = client.get_guild(guild_ids[0]).get_channel(channel_id)
        await channel.purge(limit=None, check=lambda msg: not msg.pinned)
    return True

# Create channels for users.
# Channels inherit base permissions from category channel modchat, so hidden from non-mod users by default
async def create_modchat_channel(member):
    usertag = member.name+"#"+member.discriminator
    member_unique_id = member.id
    channel_title = usertag
    if (member.display_name):
        channel_title = member.display_name

    # Get any open Chat with Moderators channel
    for channel in client.get_all_channels():
        if(channel.name=="Chat with Moderators"):
            modchat = client.get_guild(guild_ids[0]).get_channel(channel.id)
            if (len(modchat.channels)<50): # There is a 50 channel per category channel limit
                newchannel = await client.get_guild(guild_ids[0]).create_text_channel(channel_title, category=modchat)
                await newchannel.set_permissions(member,view_channel=True)
                await newchannel.send(MSG_on_modchat_open)
                return newchannel
    # Yet unable to find space in any appropriate Category Channel so try to create a new one
    modchat = await modchat.clone(name="Chat with Moderators", reason="Other Chat with Moderators category channels were full already.")
    newchannel = await client.get_guild(guild_ids[0]).create_text_channel(channel_title, category=modchat)
    await newchannel.set_permissions(member,view_channel=True)
    await newchannel.send(MSG_on_modchat_open)
    return newchannel

# create a new user log in botmemory
async def new_botmemory_log(member):
    mem_id = member.id
    usertag = member.name+"#"+member.discriminator
    if mem_id in client.botmemory:
        print("hey! user exists already!")
        return False
    botchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["botchannel"])
    client.botmemory[mem_id] = dict()
    # Enter the new user into permanent botmemory and get the ID of the message
    mem_msg = await botchannel.send(str(mem_id)+":"+usertag) #mem_msg is the message in permanent memory (aka, the bot-memory channel)
    client.botmemory[mem_id]['msgid']=mem_msg.id # Track the permanent msg id in volatile memory
    client.botmemory[mem_id]['usertag'] = usertag
    client.botmemory[mem_id]['nick'] = member.nick #The user nickname
    client.botmemory[mem_id]['reset_cooldown_flag'] = {"setemail": False, "setname": False}
    client.botmemory[mem_id]['member'] = False
    client.botmemory[mem_id]['setname'] = dict()
    client.botmemory[mem_id]['setname']['msgID'] = None # the snowflake for the interaction for this command
    client.botmemory[mem_id]['setname']['requested'] = None # most recently requested nickname 
    # previously was [num tries, lastest request msg ID, lastest approved nickname]
    client.botmemory[mem_id]['setemail'] = dict()
    client.botmemory[mem_id]['setemail']['edu_override'] = False    
    client.botmemory[mem_id]['setemail']['msgID']=None
    client.botmemory[mem_id]['setemail']['secret']=None
    client.botmemory[mem_id]['setemail']['email']={'email':None,'verified':False} #the current email and if it was verified
    client.botmemory[mem_id]['setemail']['oldverifiedemails']=[] # old emails that were verified
    # [num tries, lastest request msg ID, latest secret, latest email, T/F email passed verification]
    client.botmemory[mem_id]['modchat'] = None # will contain channel ID when it exists
    oldentry = await botchannel.fetch_message(client.botmemory[mem_id]['msgid'])
    your_data = client.botmemory[mem_id] # pickle the dictionary to be stored
    print(mem_id, client.botmemory[mem_id]['usertag'],your_data)
    pickled = codecs.encode(pickle.dumps(your_data), "base64").decode() # get a string we can safely write (codecs n stuff)
    updated = str(mem_id)+":"+usertag+':'+pickled
    await oldentry.edit(content=updated)

async def update_botmemory_log(member):
    mem_id = member.id
    usertag = member.name+"#"+member.discriminator    
    if mem_id not in client.botmemory:
        print("hey! user id: "+str(mem_id)+" doesn't exist yet in botmemory!")
        return False
    botchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["botchannel"])    
    oldentry = await botchannel.fetch_message(client.botmemory[mem_id]['msgid'])
    your_data = client.botmemory[mem_id] # pickle the dictionary to be stored
    print(mem_id, member.name+"#"+member.discriminator,your_data)
    pickled = codecs.encode(pickle.dumps(your_data), "base64").decode() # get a string we can safely write (codecs n stuff)
    updated = str(mem_id)+":"+usertag+':'+pickled
    await oldentry.edit(content=updated)


async def load_botmemory():
    # note, at some point you will be rate limited if there are too many messages to load (too many users), so think about that
    botchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["botchannel"])
    async for msg in botchannel.history(limit=None):
        if(len(msg.content.split(':'))==3): # message represents a user
            member_unique_id,member_unique_name,payload = msg.content.split(':')
            member_unique_id = int(member_unique_id) # because it was stored as string
            unpickled = pickle.loads(codecs.decode(payload.encode(), "base64"))
            client.botmemory[member_unique_id]=unpickled
            for item in ['setname','setemail']:
                msgID = client.botmemory[member_unique_id][item]['msgID']
                if(msgID!=None):
                    client.botmemory[msgID]=dict()
                    client.botmemory[msgID]['user'] = member_unique_id
                    client.botmemory[msgID]['command'] = item  
            #print(member_unique_id,member_unique_name,unpickled)

@client.event
async def on_ready():
    await load_botmemory()
    client.clean_modchat = modchatcog()
    await review_webhooks()
    print('We have logged in as {0.user}\n'.format(client))

    await client.wait_until_ready()
    if not client.added:
        # This seems to work, but it a bit weird
        # I figured I'd need to add every new view created (one per user interaction that must persist)
        # but it seems like I can just add a newly created object, and it works even if they all have the same custom_ids...?
        client.add_view(SetnameView())
        client.add_view(SetemailView())
        client.added = True
    if not client.synced:
        await tree.sync(guild = discord.Object(id=guild_ids[0]))
        client.synced = True    
    #await delete_debug_messages([channel_ids["modchannel"],channel_ids["webhooks"]])


async def review_webhooks():
    #review any messages in the webhooks channel that may have been missed
    webhooks = client.get_guild(guild_ids[0]).get_channel(channel_ids["webhooks"])
    async for msg in webhooks.history(limit=None):
        await on_message(msg) 

class modchatcog(commands.Cog):
    def __init__(self):
        self.clean_modchat.start()

    def cog_unload(self):
        self.clean_modchat.cancel()

    # to do change to reasonable number of hours
    @tasks.loop(hours=6.0)
    async def clean_modchat(self):
        print("Running clean modchat.")
        for categoryid in channel_ids["modchat"]:
            modchat = client.get_guild(guild_ids[0]).get_channel(categoryid)
            for channel in modchat.channels:
                async for msg in channel.history(limit=1):
                    lastmsgtime = msg.created_at
                    if(msg.edited_at!=None):
                        lastmsgtime = msg.edited_at
                    if (datetime.datetime.now()- lastmsgtime.replace(tzinfo=None) > datetime.timedelta(days=3)):
                        # remove the old channel
                        await channel.delete(reason="Inactivity.")

@client.event
async def on_member_update(before,after):
    # todo notify the member if they gain the role of Member? maybe just do this at the point where the mods assign the user, not here
    # if a member gets the Member role, write that down
    if ((not before.get_role(MEMBER_ROLE_ID)) and after.get_role(MEMBER_ROLE_ID)):
        client.botmemory[after.id]['member'] = True
        await update_botmemory_log(client.get_guild(guild_ids[0]).get_member(after.id))        
    # if a member loses the Member role, write that down as well
    if ((not after.get_role(MEMBER_ROLE_ID)) and before.get_role(MEMBER_ROLE_ID)):
        client.botmemory[after.id]['member'] = False
        await update_botmemory_log(client.get_guild(guild_ids[0]).get_member(after.id))

@client.event
async def on_member_join(member):
    # if the member is already in the memory
    if(member.id in client.botmemory):
        # set their nickname to whatever was saved
        nick = client.botmemory[member.id]['nick']
        if (nick is not None):
            await client.get_guild(guild_ids[0]).get_member(member.id).edit(nick=nick)
        # set their permission to member (if they left and lost it)
        if (client.botmemory[member.id]['member']):
            role = client.get_guild(guild_ids[0]).get_role(MEMBER_ROLE_ID) #Get the member role
            await member.add_roles(role)
    else: # was not in memory
        await new_botmemory_log(member)
        user = await client.fetch_user(member.id)
        await user.send(helpcontent)

@client.event
async def on_message(message):
    if (message.channel.id == channel_ids["webhooks"]):
        # Parse the message
        try:
            mandate,member_unique_id,email,secret = message.content.split('\n')
            member_unique_id = int(member_unique_id) #Since it was sent as a string message
            modchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["modchannel"])  
            if(client.botmemory[member_unique_id]['setemail']['email']['email']==email and client.botmemory[member_unique_id]['setemail']['secret'] == secret and mandate == "verify"):
                # Get the email verify request msg object
                oldmsg = await modchannel.fetch_message(client.botmemory[member_unique_id]['setemail']['msgID'])
                client.botmemory[member_unique_id]['setemail']['email']['verified']=True # Save that we verified this email
                await update_botmemory_log(client.get_guild(guild_ids[0]).get_member(member_unique_id))
                #Un-disable the button only if the user set a name already
                if(client.botmemory[member_unique_id]['nick']==None and client.get_guild(guild_ids[0]).get_member(member_unique_id).nick==None):
                    content = oldmsg.content.replace('has yet to verify','verified') + "\nNote! User still needs to set an approved name."
                    await oldmsg.edit(content=content)
                #User name is already set
                else:
                    content = oldmsg.content.replace('has yet to verify','verified')
                    if "If you trust this user" not in content:
                        content = content +"\nIf you trust this user, press the button to assign them the role of Member.\n"
                    # Edit the message and enable the button
                    setemailview = SetemailView() # create a new view
                    await oldmsg.edit(content=content,view=setemailview)
                    client.add_view(setemailview,message_id=oldmsg.id)
                    # send the user a DM
                    user = await client.fetch_user(member_unique_id)
                    await user.send(MSG_confirm_email_verified)
            else:
                # Notify the mods of this fishy webhook
                msgid = await modchannel.send(f"Warning, fishy webhook!```\n{message.content}```")
            await message.delete()
        except Exception as e:
            print("Error processing webhook! Did a message get here accidentally?")
            print(e)

class SetemailViewDisabled(discord.ui.View):
    #Buttons and callbacks for setname slash command
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Assign Member Role",style=discord.ButtonStyle.blurple,custom_id="assign",disabled=True)
    async def assign(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

class SetemailView(discord.ui.View):
    #Buttons and callbacks for setname slash command
    def __init__(self):
        super().__init__(timeout=None)
    async def deleteold(self, msgid,mem_id):
        # Function to reset the setname oldmsgid to None because we are done with this interaction forever.
        try:
            del client.botmemory[msgid]
        except KeyError:
            print("Tried to delete an interaction key but it wasn't there.")
        client.botmemory[mem_id]['setemail']['msgID']=None
        client.botmemory[mem_id]['setemail']['secret']=None
        # update the permanent memory
        await update_botmemory_log(client.get_guild(guild_ids[0]).get_member(mem_id))

    @discord.ui.button(label="Assign Member Role",style=discord.ButtonStyle.blurple,custom_id="assign",disabled=False)
    async def assign(self, interaction: discord.Interaction, button: discord.ui.Button):
        # When a moderator presses the Assign Member Role button, this happens
        msgid = interaction.message.id
        member_unique_id = client.botmemory[msgid]['user'] 
        role = client.get_guild(guild_ids[0]).get_role(MEMBER_ROLE_ID) #Get the member role
        member = client.get_guild(guild_ids[0]).get_member(member_unique_id)
        await member.add_roles(role)
        new_content = client.botmemory[member_unique_id]['usertag']+ f" was assigned the Member role by {client.get_guild(guild_ids[0]).get_member(interaction.user.id).mention}."
        await interaction.message.edit(content=interaction.message.content.split('\n')[0]+"\n"+new_content,view=None) # update it and remove the buttons
        await self.deleteold(msgid,member_unique_id)

# Set up slash command to verify your email
@tree.command(name="setemail",guild=discord.Object(id=guild_ids[0]),description="Verify your school email")
@app_commands.checks.cooldown(3,86400,key= lambda i: (i.guild_id, i.user.id)) # three tries a day
async def self(interaction: discord.Interaction, email: str):
    member_unique_id = interaction.user.id
    # If the user is already in botmemory
    if( member_unique_id not in client.botmemory):
        await new_botmemory_log(interaction.user)
    # If not an .edu, return
    if(email[-4:]!=".edu" and not client.botmemory[member_unique_id]['setemail']['edu_override']):
        await interaction.response.send_message(f"Use your academic email address or contact the moderators for an override.",ephemeral=True)
        return False
    oldemail = client.botmemory[member_unique_id]['setemail']['email']['email']
    oldemails = client.botmemory[member_unique_id]['setemail']['oldverifiedemails']
    oldstatus = client.botmemory[member_unique_id]['setemail']['email']['verified']
    if ((oldstatus == True and oldemail == email) or email in oldemails): # the user is trying to verify the same email again
        await interaction.response.send_message(f"This email is already verified. Contact the moderators for additional help.",ephemeral=True)
        return False

    # if the user wants to register a new email after having verified the last one
    if (oldstatus):
        # move their old verified email to old emails
        client.botmemory[member_unique_id]['setemail']['oldverifiedemails'].append(oldemail)

    client.botmemory[member_unique_id]['setemail']['email']['email'] = email # store the requested email
    client.botmemory[member_unique_id]['setemail']['email']['verified'] = False # this is a new email to be verified
    modchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["modchannel"])
    botchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["botchannel"])
    # Give an ephemeral confirmation message to the user initiating
    await interaction.response.send_message(f"Verification email sent to **{email}**",ephemeral=True)
    oldmsgid = client.botmemory[member_unique_id]['setemail']['msgID'] # the msg id of the last name request
    if (oldmsgid is None): # there is no previous email request
        pass
    else: # there is a previous email request, so modify it
        try:
            oldmsg = await modchannel.fetch_message(oldmsgid) # get the last name request msg object
            modified = "~~"+ oldmsg.content + "~~" # modify language
            await oldmsg.edit(content=modified,view=None) # update it and remove the buttons
            try:
                del client.botmemory[oldmsgid]
            except KeyError:
                print("Tried to delete an interaction key but it wasn't there.")
        except Exception as e:
            print(e)
    #URL of the Google Apps Script App
    url = GAS_URL
    #Generate a random secret and add it to the botmemory
    secret = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    client.botmemory[member_unique_id]['setemail']['secret'] = secret # store the secret
    #Bot fills in the data payload here
    #TODO replace token with something better. Token just authenticates bot to the GAS script
    usertag = client.botmemory[member_unique_id]['usertag']
    data = {'useremail':email,'token':GAS_TOKEN,'secret':secret, 'memberid':member_unique_id,'userhandle':usertag}
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    r = requests.post(url, params=data, headers=headers)
    #get response and make sure it isn't invisible if it fails or succeeds
    print("Server says:")
    print(r.text)
    if (interaction.user.nick):
        realname = " (_" + interaction.user.nick + "_) "
    else:
        realname = ""
    # No need to add_view for the following, because it is just a placeholder until a non-disabled view is created
    msg = await modchannel.send(
        f"`setemail` **{usertag}**: {realname} has yet to verify email address __{email}__",view=SetemailViewDisabled())
    # write to the volatile memory
    msgid = msg.id
    client.botmemory[member_unique_id]['setemail']['msgID'] = msgid # update to point to newly created request
    client.botmemory[msgid]=dict()
    client.botmemory[msgid]['user'] = member_unique_id
    client.botmemory[msgid]['command'] = 'setemail' 

    # update the permanent memory
    user = client.get_guild(guild_ids[0]).get_member(interaction.user.id)
    await update_botmemory_log(user)   

@tree.command(name="help",guild=discord.Object(id=guild_ids[0]),description="Display help information.")
async def self(interaction: discord.Interaction):
    # Give an ephemeral confirmation message to the user initiating
    await interaction.response.send_message(helpcontent,ephemeral=True)


# Set up slash command to open a modchat
@tree.command(name="modchat",guild=discord.Object(id=guild_ids[0]),description="Open a channel where you can chat privately with the server moderators.")
@app_commands.checks.cooldown(2,60,key= lambda i: (i.guild_id, i.user.id)) # why not limit to once every 30 seconds in case the bot ends up rate limited
async def self(interaction: discord.Interaction):
    existing_id = None
    try: #if the user is not in botmemory, this will raise KeyError
        existing_id = client.botmemory[interaction.user.id]['modchat']
    except KeyError:
        # Note that this might happen unintentionally if load_botmemory run at start is delayed
        await new_botmemory_log(interaction.user)
    try:
        if(existing_id!=None):
            # if the user already has a modchat channel live, don't open it, just remind them
            modchat = client.get_guild(guild_ids[0]).get_channel(existing_id)
            await interaction.response.send_message(f"Your modchat channel already exists at <#{modchat.id}>.",ephemeral=True)
            return
    except AttributeError:
        print("We had an existing modchat channel id, but were unable to retrieve the channel.")
        print("Usually this means it was deleted due to inactivity.")
    try:
        # create a new channel for the user
        modchat = await create_modchat_channel(interaction.user)
        # If the user needs to be created
        if( interaction.user.id not in client.botmemory):
            await new_botmemory_log(interaction.user)
        client.botmemory[interaction.user.id]['modchat'] = modchat.id
        # update the permanent memory
        await update_botmemory_log(client.get_guild(guild_ids[0]).get_member(interaction.user.id))
        # Give an ephemeral confirmation message to the user initiating
        await interaction.response.send_message(f"A new channel has been opened at <#{modchat.id}>.",ephemeral=True)
    except Exception as e:
        print("Issue opening a new chat!")
        print(e)
        # Give an ephemeral confirmation message to the user initiating
        await interaction.response.send_message(f"Something went wrong. Please message {client.get_guild(guild_ids[0]).get_member(SERVER_OWNER_ID).mention}.",ephemeral=True)

class SetnameView(discord.ui.View):
    #Buttons and callbacks for setname slash command
    def __init__(self):
        super().__init__(timeout=None)

    async def deleteold(self, msgid,member_unique_id):
        # Function to reset the setname oldmsgid to None because we are done with this interaction forever.
        try:
            del client.botmemory[msgid]
        except KeyError:
            print("Tried to delete an interaction key but it wasn't there.")
        client.botmemory[member_unique_id]['setname']['msgID']=None
        # Whether approved or denied, we want to clear the last request as it isn't valid anymore
        client.botmemory[member_unique_id]['setname']['requested'] = None
        # update the permanent memory
        await update_botmemory_log(client.get_guild(guild_ids[0]).get_member(member_unique_id))

    @discord.ui.button(label="Approve",style=discord.ButtonStyle.green,custom_id="approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # When a moderator presses the Approve button, do these (7) things
        member_unique_id = client.botmemory[interaction.message.id]['user']
        requested = client.botmemory[member_unique_id]['setname']['requested']
        oldmsgid = client.botmemory[member_unique_id]['setname']['msgID']
        #(1) Update the interaction message to provide receipt
        modchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["modchannel"])
        oldmsg = await modchannel.fetch_message(oldmsgid) # get the last name request msg object
        modified = f"{client.get_guild(guild_ids[0]).get_member(interaction.user.id).mention} "\
            f"approved {client.botmemory[member_unique_id]['usertag']}'s "\
            f"request to change their name to **{requested}**."
        await oldmsg.edit(content=modified,view=None) # update it and remove the buttons 
        try:
            #(2) Edit the nickname of the user whose request was approved
            await client.get_guild(guild_ids[0]).get_member(member_unique_id).edit(nick=requested)
            #(3)Write to the volatile memory
            client.botmemory[member_unique_id]['nick'] = requested # store the nickname

            # (4) if there is an open Assign Member interaction that was waiting on choosing a nickname, then we should un-disable the setemail view
            if (client.botmemory[member_unique_id]['setemail']['msgID']!=None and client.botmemory[member_unique_id]['setemail']['email']['verified']):
                modchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["modchannel"])
                oldmsg = await modchannel.fetch_message(client.botmemory[member_unique_id]['setemail']['msgID'])
                setemailview = SetemailView() # create a new view
                await oldmsg.edit(view=setemailview)
                client.add_view(setemailview,message_id=oldmsg.id)

            #(5)Notify the user throough a direct message
            await client.get_guild(guild_ids[0]).get_member(member_unique_id).send(""
                "Your request has been approved! Your nickname on the "+SERVER_NAME+" server has been changed to '"
                f"{requested}"
                "'.")
            #(6)Rename the user's modchat channel if it exists
            if (client.botmemory[member_unique_id]['modchat']!=None):
                try:
                    channel = client.get_guild(guild_ids[0]).get_channel(client.botmemory[member_unique_id]['modchat'])
                    await channel.edit(name=requested)
                except Exception as e:
                    print("Could not rename the modchat, probably because it was already deleted due to inactivity.")
        except Exception as e:
            print(e)

        #(7)Delete the old message id from the dictionary
        await self.deleteold(oldmsgid,member_unique_id)

    @discord.ui.button(label="Deny",style=discord.ButtonStyle.red,custom_id="deny")
    async def deny(self, interaction: discord.Interaction,button: discord.ui.Button):
        # If the moderator denies teh request, do these two things
        member_unique_id = client.botmemory[interaction.message.id]['user']
        requested = client.botmemory[member_unique_id]['setname']['requested']
        oldmsgid = client.botmemory[member_unique_id]['setname']['msgID']
        #(1) Update the interaction message
        modchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["modchannel"])
        oldmsg = await modchannel.fetch_message(oldmsgid) # get the last name request msg object
        modified = f"{client.get_guild(guild_ids[0]).get_member(interaction.user.id).mention} "\
            f"denied {client.botmemory[member_unique_id]['usertag']}'s "\
            f"request to change their name to **{requested}**."
        await oldmsg.edit(content=modified,view=None) # update it and remove the buttons   
        #(2) Notify the user
        await client.get_guild(guild_ids[0]).get_member(member_unique_id).send(""
            "Your request to change your server nickname to '"
            f"{requested}"
            "' has been denied by the moderators.")
        #Delete the old message id from the dictionary
        await self.deleteold(oldmsgid,member_unique_id)

@tree.command(name="repermit",guild=discord.Object(id=guild_ids[0]), description="Reset command cooldowns for a user.")
@app_commands.default_permissions(manage_roles = True)
async def self(interaction: discord.Interaction, user: discord.Member):
    client.botmemory[user.id]['reset_cooldown_flag']= {"setemail": True, "setname": True}
    userid = user.id
    usernick = client.botmemory[userid]['nick']
    usertag = client.botmemory[userid]['usertag']
    userinfo = usertag
    if usernick!=None:
        userinfo=usertag+" ("+usernick+")"
    await interaction.response.send_message(content=f"You have granted user **{userinfo}** a cooldown reset.",ephemeral=True)

@tree.command(name="edu_override",guild=discord.Object(id=guild_ids[0]), description="Allow a user to register non '.edu' emails.")
@app_commands.default_permissions(manage_roles = True)
async def self(interaction: discord.Interaction, user: discord.Member):
    client.botmemory[user.id]['setemail']['edu_override']=True
    await update_botmemory_log(client.get_guild(guild_ids[0]).get_member(user.id))
    userid = user.id
    usernick = client.botmemory[userid]['nick']
    usertag = client.botmemory[userid]['usertag']
    userinfo = usertag
    if usernick!=None:
        userinfo=usertag+" ("+usernick+")"
    await interaction.response.send_message(content=f"You have granted user **{userinfo}** permission to register non '.edu' emails.",ephemeral=True)    

@tree.command(name="setname",guild=discord.Object(id=guild_ids[0]),description="Set your full name to participate on this server (mods will review).")
@app_commands.checks.cooldown(3,86400,key= lambda i: (i.guild_id, i.user.id)) # three tries a day
async def self(interaction: discord.Interaction, name: str):
    # Give an ephemeral confirmation message to the user initiating
    await interaction.response.send_message(f"Your request has been forwarded to the moderators.",ephemeral=True)
    user = client.get_user(interaction.user.id)
    userid = user.id

    modchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["modchannel"])
    botchannel = client.get_guild(guild_ids[0]).get_channel(channel_ids["botchannel"])
    
    # If the user is already in botmemory
    if( userid in client.botmemory):
        oldmsgid = client.botmemory[userid]['setname']['msgID'] # the msg id of the last name request
        client.botmemory[userid]['setname']['requested'] = None # reset requested to None, as we are invalidating this request
        if (oldmsgid is None): # there is no previous name request
            pass
        else: # there is a previous name request, so modify it by crossing it out
            try:
                oldmsg = await modchannel.fetch_message(oldmsgid) # get the last name request msg object
                modified = "~~"+ oldmsg.content+"~~" # modify language
                await oldmsg.edit(content=modified,view=None) # update it and remove the buttons 
                try:
                    del client.botmemory[oldmsgid]
                except KeyError:
                    print("Tried to delete an interaction key but it wasn't there.")
            except Exception as e:
                print(e)
    else: # user is new, create entry in permanent and volatile botmemory
        print("Making a new log in the botmemory")
        await new_botmemory_log(interaction.user)

    # Put this request in the moderator-only channel
    formerly=""
    if (client.botmemory[userid]['nick']):
        formerly = " (_"+client.botmemory[userid]['nick']+"_) "
    usertag = client.botmemory[userid]['usertag']
    setnameview = SetnameView() # create a new view
    msg = await modchannel.send(
        f"`setname` **{usertag}**:"+ formerly +f" wants to change their name to **{name}**",view=setnameview)
    client.add_view(setnameview,message_id=msg.id)
    # write to the volatile memory
    msgid = msg.id
    client.botmemory[userid]['setname']['msgID'] = msgid # update to point to newly created request
    client.botmemory[msgid]=dict()
    client.botmemory[msgid]['user'] = user.id
    client.botmemory[msgid]['command'] = 'setname' 
    client.botmemory[userid]['setname']['requested'] = name # update the request data
    # update the permanent memory
    await update_botmemory_log(client.get_guild(guild_ids[0]).get_member(interaction.user.id))   

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        # If a mod ran the repermit command for this user to reset the cooldown for their next cooled command execution
        try:
            command_name = str(interaction.data['name'])
            if client.botmemory[interaction.user.id]['reset_cooldown_flag'][command_name]:
                error.cooldown.reset()
                data = interaction.data
                try:
                    # for commands taht have options
                    command_args_and_values = data['options']
                    dict_to_splat = {x['name']:x['value'] for x in command_args_and_values}   
                    await interaction.command.callback(interaction, **dict_to_splat)
                except KeyError:
                    # for commands that have no options
                    await interaction.command.callback(interaction)
                # reset the flag
                client.botmemory[interaction.user.id]['reset_cooldown_flag'][command_name] = False
            else: # regular cooldown message
                return await interaction.response.send_message(error,ephemeral=True)
        except KeyError:
            # regular cooldown message
            return await interaction.response.send_message(error,ephemeral=True)
    else:
        await interaction.response.send_message(error,ephemeral=True)

client.run(bot_token)