# Walkthrough - Group Chatting Integration

Implemented Group Chatting on top of the direct messaging framework. Users can now create group chats with multiple participants, preview group threads with a distinct group avatar, and receive group messages in real-time with sender labels displayed above the text bubbles.

## Changes Made

### 1. Database Schema & Models
- Added the `name` column to the `conversations` table [models.py](file:///Users/alanjayan/Documents/CODE/intern/instagram/database/models.py#L373) in the database and updated both models files.

### 2. Pydantic Schemas
- **[schemas/messaging.py](file:///Users/alanjayan/Documents/CODE/intern/instagram/schemas/messaging.py)**:
  - Extended `ConversationResponse` with `name` and `member_usernames` fields.
  - Added `GroupConversationCreateRequest` schema.
  - Extended `MessageResponse` with `sender_username` and `sender_avatar`.
- **[schemas/\_\_init\_\_.py](file:///Users/alanjayan/Documents/CODE/intern/instagram/schemas/__init__.py)**: Exported the group creation request schema.

### 3. Backend Endpoints & Logic
- **[crud_messaging.py](file:///Users/alanjayan/Documents/CODE/intern/instagram/crud/crud_messaging.py#L79-L119)**:
  - Added `create_group_conversation` to construct group conversation entries and add all participant profiles as members.
  - Updated `send_message` to fetch the sender's profile and push `sender_username` and `sender_avatar` to the WS payload.
- **[main.py](file:///Users/alanjayan/Documents/CODE/intern/instagram/main.py#L678-L745)**:
  - Added the `POST /api/conversations/group` endpoint for group creation.
  - Updated `list_conversations` (GET) and message retrieval/sending routes to return sender metadata and participant list details.

### 4. UI & Layout
- **[index.html](file:///Users/alanjayan/Documents/CODE/intern/instagram/static/index.html)**:
  - Added a group chat creation trigger button next to the direct chat button in the message list sidebar.
  - Created the `#modal-new-group` modal with Group Name and comma-separated Members input fields.
  - Bumped static assets cache-busting parameter to `?v=5`.

### 5. Client Logic & Styles
- **[style.css](file:///Users/alanjayan/Documents/CODE/intern/instagram/static/style.css#L827-L840)**:
  - Styled `.msg-sender-label` for displaying sender names in group chats.
  - Styled group thread avatars (`.conv-avatar.group`) with a distinct gradient.
- **[app.js](file:///Users/alanjayan/Documents/CODE/intern/instagram/static/app.js)**:
  - Configured `#new-group-form` submission, communicating with the group creation endpoint.
  - Updated sidebar list rendering to format group rows showing the group name and a fallback list of member usernames.
  - Configured message rendering to display the sender's username above incoming messages in group chats.

## Verification Instructions

### Manual Testing Flow
1. Launch two or three separate browser sessions:
   - **User A** (e.g. `alan.05` / password `password123`)
   - **User B** (e.g. `foodie_heaven` / password `password123`)
   - **User C** (e.g. `gamer_zone` / password `password123`)
2. Logged in as User A, navigate to **Messages**.
3. Click the **Group Chat Icon** (users icon next to envelope).
4. Fill in the modal:
   - **Group Name**: `Tech & Food Chat`
   - **Members**: `foodie_heaven, gamer_zone`
5. Click **Create Group**.
6. Type a message in the chat room (e.g., "Hey everyone, welcome to the group!") and click send.
7. Verify that:
   - User B and User C receive the chat invitation / group conversation thread in their sidebar.
   - User B and User C see your message in real-time.
   - Incoming messages on User B's screen show `@alan.05` above the bubble.
   - Replying as User B displays `@foodie_heaven` above their bubble on User A and User C's screens.
