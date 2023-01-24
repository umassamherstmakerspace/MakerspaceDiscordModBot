# MakerspaceDiscordModBot
The Discord Moderator Bot for the UMass Amherst Makerspace. Assists mods with moderation.

**Basic features:**
* Welcome users to the server and provide instructions via direct message
* Provide a `/help` command for users to view instructions again via 'ephemeral' message that only they can see
* Require users to set their names and verify official .edu email addresses (`/setname`, `/setemail` commands)
* Allow users to open a private chat to all moderators using `/modchat`

**The user perspective** (new users seeking to gain Member role):
* Upon joining the server the bot DMs the help message which includes server info & instructions
* Users may run commands in select channels with appropriate permissions[^1]
* Users run `/setname` to request a name change; users will be notified when the request is approved or denied
* Users run `/setemail` to provide an .edu email that they will verify by clicking on a link that is emailed to the specified address
* Users will be notified when their email has been successfully verified
* Users can use `/modchat` to start a chat channel with moderators, for example to request an override to the .edu email requirement 

[^1]: At time of writing it is not possible for users to 'Use Application Commands' if 'Send Messages' is not also given as a permission. The originally desired behavior was to limit new users to only using these custom Application Commands except in the channel they can open with `\modchat`, however this was not compatible with the design of Discord.

**The moderator perspective:**
* Moderators are prompted to approve/deny name change requests using persistent buttons that appear in the designated moderator channel 
* Moderators can grant resets to users who have overrused commands (hit command timeouts) using mod-only command `/repermit`
* Moderators will see a message paired with a disabled "Assign Member Role" button in the designated moderator channel when users initiate a `/setemail` process
* "Assign Member Role" buttons are converted to active once the user email verification is complete AND the user has successfully changed their server Nickname (ostensibly by an approved `/setname` request)
* Moderators can use `/edu_override` requests to allow users to provide non-edu emails

**Design notes:**
* Uses a designated botmemory channel to provide the bot with a persistent memory log
* Cleans unused modchat channels after a time to avoid reaching server channel limit
* Uses a Google Apps Script (GAS) system to send out verification emails
* Stores pending verification request info in script properties, and clears entries after expiry to save space
* GAS sends webhook to Discord bot for processing when user verifies email address

**How to use:**
Note that setup is not very streamlined. You will need to do several things:
* Discord: 
  * Set up bot permissions and add your bot to the server
  * Set up your roles, category, and channel permissions to work appropriately
  * Get tokens and ids and put them in the `config.ini` file
* Google Apps Script (GAS):
  * Create a script and provide it with the GAS code and HTML files from this repository
  * Select a `GAS_TOKEN` the Discord bot will hand to the GAS script; put it in both the `config.ini` file and the GAS code
  * Deploy it and get the URL; provide that URL to the `config.ini` file
* Python script: run it
