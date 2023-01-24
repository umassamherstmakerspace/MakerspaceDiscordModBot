/
*
 * This webapp accomplishes two main functions:
 * (1) Serves the verification HTML page under the right conditions, in response to a doGet
 * (2) Sends a verification email under the right conditions, in response to a doPost
 * Fill in this first section with your specific values.
 */

// Provide the Discord Webhook URL (setup from within Discord Server Management > Integrations > Create Webhook)
const discordwebhookurl = "";

// Provide your chosen secret token that authenticates the bot making the POST requests to this web app. Needs to match what you specify in your config.ini for the bot Python script
const gastoken = "";

// Provide the server name. This will show up in the subject line and body of verifications emails sent to users.
const servername= "My Servername";

// OPTIONAL: Establish a date to serve as the beginning of time, noting time is only counted in days here.
// Changing this will invalidate any active (unexpired) verification requests users have initiated
const timereferencepoint = "09/03/2019";

// Run this function or get the URL from the Deploy menu. Provide it to the config.ini for the Pythons script
function getUrl() {
  console.log(ScriptApp.getService().getUrl());
}

function doGet(e) {
  //Serves the user the webapp.
  //Normally served when the user presses the link sent to their email
  var params = JSON.stringify(e);
  var flag=false;
  try {
    const userProperties = PropertiesService.getUserProperties();
    //check if the first part of the secret is correct
    if (userProperties.getProperty(e.parameters.memberid) == e.parameters.secret.toString()) { 
      flag = true;
    }
  }
  catch(error) {
    Logger.log(error);
  }

  if(flag) { //Serve the page
    var html = HtmlService.createTemplateFromFile('Index');
    html.servername = servername;
    html.username = e.parameters.userhandle;
    html.email = e.parameters.email;
    html.params = params;
    var output = html.evaluate();
    output.addMetaTag('viewport', 'width=device-width, initial-scale=1');
    return output;
  }
  else { //Serve the expiry page
    var html = HtmlService.createTemplateFromFile('Failure');
    var output = html.evaluate();
    output.addMetaTag('viewport', 'width=device-width, initial-scale=1');
    return output;
  }
}

function resetUserproperties() {
  //Debug function to delete all user properties
  //WARNING: will cause all active links to expire
  const userProperties = PropertiesService.getUserProperties();
  userProperties.deleteAllProperties();
}

function deleteExpired() {
  //Timer based to delete expired properties (b/c there's a 500kb storage limit)  
  //to be executed on a timer, delete properties older than X
  try { // Get multiple script properties in one call, then log them all.
  const userProperties = PropertiesService.getUserProperties();
  const data = userProperties.getProperties();
  for (const key in data) {
    if (getTimestamp() - parseInt(data[key].split('$')[1]) > 7 ) {
      Logger.log('Deleting expired Key: %s, Value: %s', key, data[key]);
      userProperties.deleteProperty(key);
    }
  }
} catch (err) {
  Logger.log('Failed with error %s', err.message);
}

}

function sendconfirmation(params,flag){
  //This function runs when the user presses the HTML confirmation button
  var t = JSON.parse(params)['parameter'];
  var state;
  const userProperties = PropertiesService.getUserProperties();
  if( userProperties.getProperty(t['memberid']) ==t['secret'] ) { //Check if the secret is correct; if it is, send a webhook
    if (flag) { state = "verify"; }
    else { state = "report"; }
    //todo, figure out format for webhook
    var secret = t['secret'].split('$')[0];
    //Content format: email /n token /n username
    data = { "content" : state+"\n"+t['memberid']+"\n"+t['email']+"\n"+secret,
          "username" : "verify-bot"};
        var options = { 'method' : 'post', 'payload' : data };
        response = UrlFetchApp.fetch(discordwebhookurl, options);
    //delete the user properties to cause this link to expire
    userProperties.deleteProperty(t['memberid']);
    }
}

function tokencheck_(token) {
  //Check that the bot provided the right token
 // Define a secret token that only the Discord Bot knows.
 // The Discord Bot should give this token in the POST request
 // If it matches, we can continue and send the verification email
 // This adds another layer of protection.
 // Somebody who has discovered the web app URL will also need a token to cause an email to fire
 // The other level of security will be that Google will throttle this script from sending excessive emails.
 return (token == gastoken) 
}

function getTimestamp(){
  //Get the floor of the number of days since the beginnning of time
  var zerodate = new Date(timereferencepoint);
  var date2 = Date.now();
  return Math.floor((date2 - zerodate.getTime())/ (1000 * 3600 * 24));
}

function testTimestamp(){
  Logger.log(getTimestamp());
}

function doPost(e){
  buttonurl = ScriptApp.getService().getUrl()+"?";
  //Used by the bot to generate the email, only if the bot can provide the correct token
  var t = JSON.parse(JSON.stringify(e))['parameter']; //Get the payload in a format we can use
  if(tokencheck_(t['token'])) {  //if we have the right token
    try {
      const userProperties = PropertiesService.getUserProperties();
      secretwithtime = t['secret'].concat('$',getTimestamp().toString());
      userProperties.setProperty(t['memberid'],secretwithtime);
      
      var templ = HtmlService.createTemplateFromFile('Email');
      templ.userhandle = t['userhandle'];
      
      buttonurl = buttonurl + "userhandle=" + t['userhandle'].replace('#',"%23");
      buttonurl = buttonurl + "&email="+t['useremail'].replace('@',"%40");
      buttonurl = buttonurl + "&secret=" + secretwithtime.replace('$',"%24");
      buttonurl = buttonurl + "&memberid="+ t['memberid'];

      templ.buttonurl = buttonurl;
      templ.servername = servername;
      var message = templ.evaluate().getContent();
      MailApp.sendEmail({
        to: t['useremail'],
        subject: "Verify your email for the "+servername+" Discord Server "+t['userhandle'],
        htmlBody: message
      });
      }
    catch (error) {
      Logger.log(error);
       //NOTE: this only catches really obvious issues.
       //IN fact, it will still run with a set of email addresses that the Gmail UI considers malformed
       //There is no obvious way to catch this; it doesn't even always bounce the email
       //The Discord Bot will be responsible to confirm the user input to the user in a DM
       //The user will be responsible to double checking the accuracy of the input they provided.
       return ContentService.createTextOutput(error)
     }
    return ContentService.createTextOutput("Sent email to: "+String(t['useremail'])+", asking to verify: "+String(t['userhandle']))
  }

  else{
    return ContentService.createTextOutput("Token incorrect.")
  }
}



