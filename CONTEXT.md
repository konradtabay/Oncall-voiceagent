# On-call voice

A Maintainer gets a phone call when a watched process goes down and stays on the line while the Cloud Agent carries out the one Fix. The call ends when the process is verified back up.

## Language

**Maintainer**:
The one person who is called about an Incident and who can tell the Cloud Agent to Execute.
_Avoid_: user, on-call, contact

**Incident**:
A watched process that an outside alert says is down.
_Avoid_: crash, outage, alert (the alert opens it; the Incident is the down process)

**Cloud Agent**:
The agent that owns an Incident. It understands the failure, speaks with the Maintainer, and can change the server.
_Avoid_: voice agent, bot, the model

**Voice Session**:
The live phone call in which the Cloud Agent speaks with the Maintainer.
_Avoid_: the agent (when you mean the call)

**Text Session**:
The SMS conversation with the Cloud Agent after a Miss. It stays open through the Fix and Verify, and it ends at Close.
_Avoid_: WhatsApp, chat, notification

**Brief**:
The spoken or written account of what broke and the situation around it, in plain language a fifteen-year-old would follow, with no padding and no raw error dump.
_Avoid_: summary, diagnosis, error message

**Fix**:
The one repair the Cloud Agent will make on the server so the process runs again.
_Avoid_: solution, patch, option, options

**Execute**:
The Maintainer's explicit instruction to carry out the Fix. It counts only when it is still the last thing they asked for when the Fix starts.
_Avoid_: yes, approval, decision

**Verify**:
The Cloud Agent's check that the process is back up and running after a Fix.
_Avoid_: healthcheck, ping

**Close**:
The end of the Voice Session or the Text Session, once Verify has succeeded.
_Avoid_: goodbye

**Drop**:
The Maintainer's instruction to abandon the current Incident without carrying out a Fix.
_Avoid_: cancel, never mind

**Miss**:
A Voice Session the Maintainer did not take. No answer, busy, declined, and a machine pickup are all a Miss.
_Avoid_: voicemail, no-pickup

**Receipt**:
A one-way plain-language SMS that records an issue and what was done about it. Sending one does not open a conversation.
_Avoid_: text session, notification, log, transcript

**Follow-up**:
A text the Maintainer sends to the Cloud Agent after a Receipt.
_Avoid_: reply thread, chat
