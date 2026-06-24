/**
 * Instagram Clone Single-Page App Logic
 */

// Global state
let state = {
  token: localStorage.getItem("authToken") || "",
  profile: null,
  activeTab: "feed",
  activeConversationId: null,
  activeConversationPartner: null,
  activeConversationIsGroup: false,
  activeConversationGroupName: null,
  storyTimer: null,
  viewingUsername: null,
  socket: null
};

// ==========================================
// SAFE ID COMPARISON (fixes 2^x large integer / randbits precision bug)
// JavaScript Numbers lose precision for integers > 2^53. Large DB IDs (e.g.
// PostgreSQL BIGINT) can exceed this, causing === equality to silently fail.
// Always compare IDs as strings to avoid this.
function sameId(a, b) {
  if (a == null || b == null) return false;
  return String(a) === String(b);
}

// ==========================================
// TOAST NOTIFICATION SYSTEM
// ==========================================
function showToast(message, type = "error") {
  // Remove any existing toast
  const existing = document.getElementById("app-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "app-toast";
  const colors = {
    error: "#e74c3c",
    success: "#27ae60",
    info: "#3498db",
    warning: "#f39c12"
  };
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: ${colors[type] || colors.error};
    color: #fff;
    padding: 14px 20px;
    border-radius: 10px;
    font-size: 0.9rem;
    font-weight: 500;
    z-index: 99999;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    max-width: 360px;
    word-break: break-word;
    animation: slideInRight 0.3s ease;
    display: flex;
    align-items: center;
    gap: 10px;
  `;
  const icon = { error: "⚠️", success: "✅", info: "ℹ️", warning: "⚡" }[type] || "⚠️";
  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  document.body.appendChild(toast);

  // Add animation keyframe if not already present
  if (!document.getElementById("toast-style")) {
    const style = document.createElement("style");
    style.id = "toast-style";
    style.textContent = `
      @keyframes slideInRight {
        from { opacity: 0; transform: translateX(60px); }
        to   { opacity: 1; transform: translateX(0); }
      }
    `;
    document.head.appendChild(style);
  }

  setTimeout(() => { if (toast.parentNode) toast.remove(); }, 4000);
}

// API Helpers
async function apiRequest(path, method = "GET", body = null) {
  const headers = {
    "Content-Type": "application/json"
  };
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }

  const options = { method, headers };
  if (body) {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(path, options);
    if (response.status === 401) {
      // Only force logout if the user was previously logged in (not during login request itself)
      if (path !== "/api/login" && state.profile) {
        logout();
        showToast("Session expired. Please log in again.", "warning");
      }
      throw new Error("Session expired. Please log in again.");
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Something went wrong");
    }
    return data;
  } catch (error) {
    console.error(`API Error on ${path}:`, error);
    // Show toast only for non-network / non-abort errors and avoid spamming on feed sub-requests
    if (!error.message.includes("Session expired") || path === "/api/login") {
      showToast(error.message, "error");
    }
    throw error;
  }
}

// ==========================================
// APP INITIALIZATION
// ==========================================
window.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  if (state.token) {
    loadApp();
  } else {
    showAuthScreen();
  }
});

function showAuthScreen() {
  document.getElementById("auth-screen").classList.remove("hidden");
  document.getElementById("main-app").classList.add("hidden");
}

function connectWebSocket() {
  if (state.socket) {
    try {
      state.socket.close();
    } catch (e) {}
    state.socket = null;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/api/ws?token=${state.token}`;
  
  console.log("Connecting to WebSocket:", wsUrl);
  const socket = new WebSocket(wsUrl);
  state.socket = socket;

  socket.onopen = () => {
    console.log("WebSocket connection established");
  };

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      console.log("WebSocket event received:", payload);
      
      if (payload.type === "message") {
        const msg = payload.data;
        if (sameId(state.activeConversationId, msg.conversation_id)) {
          appendMessageToUI(msg);
          if (!sameId(msg.sender_id, state.profile && state.profile.profile_id)) {
            triggerMarkSeen(msg.message_id);
          }
        } else {
          showToast(`New message: ${msg.content}`, "info");
        }
        // Always refresh conversations to update the last message preview
        if (state.activeTab === "messages") {
          fetchConversations();
        }
      } else if (payload.type === "new_conversation") {
        const conv = payload.data;
        showToast(`Added to new group: ${conv.name}`, "info");
        if (state.activeTab === "messages") {
          fetchConversations();
        }
      } else if (payload.type === "notification") {
        // Ignore duplicate toast notifications for messages
        if (payload.data && payload.data.notification_type === "message") {
          return;
        }
        showToast(payload.data.content || "New notification received", "info");
      }
    } catch (err) {
      console.error("Error processing WS message:", err);
    }
  };

  socket.onclose = () => {
    console.log("WebSocket connection closed");
    state.socket = null;
    if (state.token) {
      setTimeout(() => {
        if (state.token) connectWebSocket();
      }, 5000);
    }
  };

  socket.onerror = (error) => {
    console.error("WebSocket error:", error);
  };
}

function appendMessageToUI(msg) {
  const msgsContainer = document.getElementById("chat-messages-container");
  if (!msgsContainer) return;

  if (msgsContainer.querySelector(".story-expires-indicator")) {
    msgsContainer.innerHTML = "";
  }

  if (msgsContainer.querySelector(`[data-message-id="${msg.message_id}"]`)) {
    return;
  }

  // Use string comparison to avoid 2^53 large-integer precision loss
  const isOutgoing = state.profile && sameId(msg.sender_id, state.profile.profile_id);
  const reactionString = msg.emoji_reaction || "";

  const wrapper = document.createElement("div");
  wrapper.className = `msg-wrapper ${isOutgoing ? 'outgoing' : 'incoming'}`;
  wrapper.setAttribute("data-message-id", msg.message_id);

  let senderLabelHtml = "";
  if (!isOutgoing && state.activeConversationIsGroup) {
    const senderName = msg.sender_username || `user_${msg.sender_id}`;
    senderLabelHtml = `<div class="msg-sender-label">@${senderName}</div>`;
  }

  wrapper.innerHTML = `
    ${senderLabelHtml}
    <div class="msg-bubble">
      ${msg.content}
      ${reactionString ? `<div class="reactions-box">${reactionString}</div>` : ''}
    </div>
    
    <!-- Emoji trigger -->
    ${!isOutgoing ? `
      <button class="reaction-trigger-btn" onclick="reactToMessage(${msg.message_id}, '❤️')" title="React ❤️">
        <i class="fa-regular fa-heart"></i>
      </button>
    ` : ''}
  `;
  msgsContainer.appendChild(wrapper);
  msgsContainer.scrollTop = msgsContainer.scrollHeight;
}

async function loadApp() {
  document.getElementById("auth-screen").classList.add("hidden");
  document.getElementById("main-app").classList.remove("hidden");
  
  try {
    // 1. Fetch current profile (This verifies if token is working)
    state.profile = await apiRequest("/api/profile", "GET");
    console.log("Logged in user:", state.profile);
    
    // 2. Connect WebSocket
    connectWebSocket();
    
    // 3. Fetch feed, stories, DMs
    fetchFeed();
    fetchStories();
    fetchConversations();
    
    // Set UI indicators
    document.getElementById("btn-nav-profile").querySelector("span").textContent = `Profile`;
  } catch (err) {
    console.error("Failed to load application state:", err);
    logout();
  }
}

function logout() {
  if (state.token) {
    fetch("/api/logout", {
      method: "POST",
      headers: { "Authorization": `Bearer ${state.token}` }
    }).catch(() => {});
  }
  
  if (state.socket) {
    try {
      state.socket.close();
    } catch (e) {}
    state.socket = null;
  }
  
  state.token = "";
  state.profile = null;
  localStorage.removeItem("authToken");
  showAuthScreen();
}

// ==========================================
// EVENT HANDLERS & NAVIGATION
// ==========================================
function setupEventListeners() {
  // Toggle forms
  document.getElementById("to-register").addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById("login-form").classList.remove("active");
    document.getElementById("register-form").classList.add("active");
  });
  
  document.getElementById("to-login").addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById("register-form").classList.remove("active");
    document.getElementById("login-form").classList.add("active");
  });

  // Auth Submit Actions
  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username_or_email = document.getElementById("login-username").value;
    const password = document.getElementById("login-password").value;
    
    try {
      const data = await apiRequest("/api/login", "POST", { username_or_email, password });
      state.token = data.access_token;
      localStorage.setItem("authToken", state.token);
      loadApp();
    } catch (err) {}
  });

  document.getElementById("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("reg-email").value;
    const full_name = document.getElementById("reg-fullname").value;
    const username = document.getElementById("reg-username").value;
    const phone = document.getElementById("reg-phone").value || null;
    const password = document.getElementById("reg-password").value;
    
    try {
      await apiRequest("/api/register", "POST", { email, full_name, username, phone, password });
      
      // Auto-login using the credentials just submitted
      const loginData = await apiRequest("/api/login", "POST", {
        username_or_email: username,
        password: password
      });
      
      state.token = loginData.access_token;
      localStorage.setItem("authToken", state.token);
      
      // Load user profile details and redirect directly to Profile View
      await loadApp();
      switchTab("profile");
      
      // Reset form fields
      document.getElementById("register-form").reset();
    } catch (err) {}
  });

  // Logout Click
  document.getElementById("btn-logout").addEventListener("click", (e) => {
    e.preventDefault();
    logout();
  });

  // Tab Menu Switching
  document.querySelectorAll(".nav-item[data-tab]").forEach(item => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      const tab = item.getAttribute("data-tab");
      if (tab === "profile") {
        state.viewingUsername = null;
      }
      switchTab(tab);
    });
  });

  // Modals Open/Close Events
  const setupModal = (btnId, modalId, closeId) => {
    document.getElementById(btnId).addEventListener("click", (e) => {
      e.preventDefault();
      document.getElementById(modalId).classList.remove("hidden");
      if (modalId === "modal-profile" && state.profile) {
        // Populate profile inputs
        document.getElementById("edit-fullname").value = state.profile.full_name || "";
        document.getElementById("edit-username").value = state.profile.username || "";
        document.getElementById("edit-bio").value = state.profile.bio || "";
        document.getElementById("edit-website").value = state.profile.website || "";
      }
    });
    document.getElementById(closeId).addEventListener("click", () => {
      document.getElementById(modalId).classList.add("hidden");
    });
  };
  
  setupModal("btn-open-create", "modal-create", "btn-close-create");
  setupModal("profile-btn-edit", "modal-profile", "btn-close-profile");
  setupModal("btn-new-chat", "modal-new-chat", "btn-close-new-chat");
  setupModal("btn-chat-empty-start", "modal-new-chat", "btn-close-new-chat");
  setupModal("btn-new-group", "modal-new-group", "btn-close-new-group");

  // Relations modal triggers
  document.getElementById("btn-close-relations").addEventListener("click", () => {
    document.getElementById("modal-relations").classList.add("hidden");
  });

  document.getElementById("link-show-followers").addEventListener("click", (e) => {
    e.preventDefault();
    showRelationsModal("followers");
  });

  document.getElementById("link-show-following").addEventListener("click", (e) => {
    e.preventDefault();
    showRelationsModal("following");
  });

  // Avatar hover edit click
  document.getElementById("profile-avatar-wrapper").addEventListener("click", () => {
    const isOwnProfile = !state.viewingUsername || (state.profile && state.viewingUsername === state.profile.username);
    if (isOwnProfile) {
      document.getElementById("profile-btn-edit").click();
    }
  });

  // Content type change for posts/reels
  document.getElementById("create-type").addEventListener("change", (e) => {
    const val = e.target.value;
    if (val === "reel") {
      document.getElementById("grp-location").style.display = "none";
      document.getElementById("grp-duration").style.display = "block";
    } else {
      document.getElementById("grp-location").style.display = "block";
      document.getElementById("grp-duration").style.display = "none";
    }
  });

  // File upload helper function
  async function uploadFileHelper(fileInputId) {
    const fileInput = document.getElementById(fileInputId);
    if (!fileInput || fileInput.files.length === 0) return null;
    
    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append("file", file);
    
    const response = await fetch("/api/upload", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${state.token}`
      },
      body: formData
    });
    
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to upload file");
    }
    
    const data = await response.json();
    return data.url;
  }

  // Form Publishing Creation
  document.getElementById("create-post-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const type = document.getElementById("create-type").value;
    const caption = document.getElementById("create-caption").value;
    
    try {
      const mediaUrl = await uploadFileHelper("create-file");
      
      if (type === "reel") {
        const duration = parseInt(document.getElementById("create-duration").value);
        await apiRequest("/api/reels", "POST", { caption, duration, media_url: mediaUrl });
      } else {
        const location = document.getElementById("create-location").value;
        await apiRequest("/api/posts", "POST", { caption, location, media_url: mediaUrl });
      }
      
      document.getElementById("modal-create").classList.add("hidden");
      document.getElementById("create-post-form").reset();
      fetchFeed(); // Refresh posts
    } catch (err) {}
  });

  // Edit Profile Form Submit
  document.getElementById("edit-profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const full_name = document.getElementById("edit-fullname").value;
    const username = document.getElementById("edit-username").value;
    const bio = document.getElementById("edit-bio").value;
    const website = document.getElementById("edit-website").value;
    const phone = document.getElementById("edit-phone").value || null;

    try {
      let profilePictureUrl = null;
      try {
        profilePictureUrl = await uploadFileHelper("edit-profile-picture-file");
      } catch (uploadErr) {
        console.error("Profile picture upload failed, proceeding without it", uploadErr);
      }

      const body = { full_name, username, bio, website, phone };
      if (profilePictureUrl) {
        body.profile_picture = profilePictureUrl;
      }

      state.profile = await apiRequest("/api/profile", "PUT", body);
      document.getElementById("modal-profile").classList.add("hidden");
      document.getElementById("edit-profile-form").reset();
      fetchFeed();
      if (state.activeTab === "profile") {
        fetchProfilePage();
      }
    } catch (err) {}
  });

  // Story Creation Button click
  document.getElementById("btn-create-story").addEventListener("click", async () => {
    try {
      await apiRequest("/api/stories", "POST");
      fetchStories();
    } catch (err) {}
  });

  // Close Story viewer
  document.getElementById("btn-close-story-viewer").addEventListener("click", () => {
    closeStoryViewer();
  });

  // New Chat Form Submit
  document.getElementById("new-chat-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("new-chat-recipient").value;
    try {
      const conv = await apiRequest(`/api/conversations?recipient_username=${username}`, "POST");
      document.getElementById("modal-new-chat").classList.add("hidden");
      document.getElementById("new-chat-form").reset();
      
      // Refresh chats and open the conversation
      await fetchConversations();
      openChatRoom(conv.conversation_id, username);
    } catch (err) {}
  });
  // New Group Form Submit
  document.getElementById("new-group-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("new-group-name").value.trim();
    const membersText = document.getElementById("new-group-members").value.trim();
    if (!name || !membersText) return;

    const member_usernames = membersText.split(",").map(u => u.trim()).filter(Boolean);
    try {
      const conv = await apiRequest("/api/conversations/group", "POST", {
        name,
        member_usernames
      });
      document.getElementById("modal-new-group").classList.add("hidden");
      document.getElementById("new-group-form").reset();
      
      // Refresh chats and open the group conversation
      await fetchConversations();
      openChatRoom(conv.conversation_id, null, null, true, name);
    } catch (err) {
      showToast("Failed to create group conversation");
    }
  });
  // Message Send Submit
  document.getElementById("chat-input-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const textInput = document.getElementById("chat-message-text");
    const content = textInput.value.trim();
    if (!content || !state.activeConversationId) return;

    // Optimistically clear input immediately for better UX
    textInput.value = "";

    try {
      const newMsg = await apiRequest(`/api/conversations/${state.activeConversationId}/messages`, "POST", {
        content,
        message_type: "text"
      });

      // Ensure sender_id is set so appendMessageToUI knows it's outgoing
      // (some API responses omit sender_id; fall back to current user's id)
      if (!newMsg.sender_id && state.profile) {
        newMsg.sender_id = state.profile.profile_id;
      }

      appendMessageToUI(newMsg);
      // Update conversation list preview without disturbing the open chat
      fetchConversations();
    } catch (err) {
      // Restore the input text if send failed
      textInput.value = content;
      console.error("Send message error:", err);
    }
  });

  // Close Reel comments modal
  document.getElementById("btn-close-reel-comments").addEventListener("click", () => {
    document.getElementById("modal-reel-comments").classList.add("hidden");
  });

  // Reel Comment Form Submit
  document.getElementById("reel-comment-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("reel-comment-input");
    const text = input.value.trim();
    const reelId = document.getElementById("reel-comment-form").dataset.reelId;
    if (!text || !reelId) return;

    try {
      await apiRequest(`/api/reels/${reelId}/comments`, "POST", { comment_text: text });
      input.value = "";
      await loadReelComments(reelId);
    } catch (err) {}
  });

  // Live Search listener
  const searchInput = document.getElementById("search-input");
  const clearSearchBtn = document.getElementById("btn-clear-search");
  
  if (searchInput && clearSearchBtn) {
    searchInput.addEventListener("input", (e) => {
      const val = e.target.value.trim();
      if (val.length > 0) {
        clearSearchBtn.classList.remove("hidden");
        performSearch(val);
      } else {
        clearSearchBtn.classList.add("hidden");
        document.getElementById("search-results-box").classList.add("hidden");
        document.getElementById("search-explore-box").classList.remove("hidden");
      }
    });

    clearSearchBtn.addEventListener("click", () => {
      searchInput.value = "";
      clearSearchBtn.classList.add("hidden");
      document.getElementById("search-results-box").classList.add("hidden");
      document.getElementById("search-explore-box").classList.remove("hidden");
    });
  }

  // Profile posts vs reels sub-tabs toggle
  const btnProfilePosts = document.getElementById("btn-profile-posts");
  const btnProfileReels = document.getElementById("btn-profile-reels");
  
  if (btnProfilePosts && btnProfileReels) {
    btnProfilePosts.addEventListener("click", () => {
      btnProfilePosts.classList.add("active");
      btnProfileReels.classList.remove("active");
      document.getElementById("profile-posts-grid").classList.remove("hidden");
      document.getElementById("profile-reels-grid").classList.add("hidden");
    });

    btnProfileReels.addEventListener("click", () => {
      btnProfileReels.classList.add("active");
      btnProfilePosts.classList.remove("active");
      document.getElementById("profile-reels-grid").classList.remove("hidden");
      document.getElementById("profile-posts-grid").classList.add("hidden");
    });
  }
}

function switchTab(tab) {
  // Pause any active videos when navigating away from reels
  document.querySelectorAll(".reel-video-container video").forEach(v => v.pause());

  state.activeTab = tab;
  document.querySelectorAll(".nav-item[data-tab]").forEach(item => {
    item.classList.toggle("active", item.getAttribute("data-tab") === tab);
  });
  
  document.querySelectorAll(".tab-view").forEach(view => {
    view.classList.add("hidden");
  });
  document.getElementById(`tab-${tab}`).classList.remove("hidden");
  
  if (tab === "feed") {
    fetchFeed();
    fetchStories();
  } else if (tab === "messages") {
    fetchConversations();
  } else if (tab === "profile") {
    fetchProfilePage(state.viewingUsername);
  } else if (tab === "reels") {
    fetchReelsFeed();
  } else if (tab === "search") {
    fetchExploreGrid();
  }
}

// ==========================================
// FEED TAB RENDERING & LIKES/COMMENTS
// ==========================================
async function fetchFeed() {
  const postsContainer = document.getElementById("feed-posts");
  postsContainer.innerHTML = `<div class="story-expires-indicator"><i class="fa-solid fa-spinner fa-spin"></i> Loading Feed...</div>`;
  
  try {
    const feed = await apiRequest("/api/posts/feed");
    postsContainer.innerHTML = "";
    
    if (feed.length === 0) {
      postsContainer.innerHTML = `
        <div class="chat-empty-state" style="margin-top: 50px;">
          <i class="fa-regular fa-image"></i>
          <h3>No Posts Yet</h3>
          <p>Follow users or post content yourself to see dynamic feed updates here.</p>
        </div>
      `;
      return;
    }
    
    // Sort feed items descending (redundancy safety)
    for (const post of feed) {
      // Determine if post is a Reel (using visibility/caption metadata or just a check)
      const isReel = post.location === null && post.visibility === "reel_simulation"; // Simple metadata tag simulation
      
      // Fetch likes list for this post from MongoDB
      let likes = [];
      try {
        likes = await apiRequest(`/api/likes?target_id=${post.post_id}&target_type=post`);
      } catch (err) {}
      
      const likeCount = likes.length;
      const isLikedByMe = likes.some(l => l.profile_id === state.profile.profile_id);
      
      // Fetch Comments list
      let comments = [];
      try {
        comments = await apiRequest(`/api/posts/${post.post_id}/comments`);
      } catch (err) {}
      
      const card = document.createElement("div");
      card.className = "post-card";
      const avatarHtml = post.profile_picture 
        ? `<img src="${post.profile_picture}" alt="${post.username || 'user'}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">` 
        : (post.username ? post.username.substring(0, 2).toUpperCase() : 'U');

      let mediaHtml = '';
      if (post.media_url) {
        const isVideo = post.media_url.match(/\.(mp4|webm|ogg|mov|m4v)$/i) || post.visibility === 'reel';
        if (isVideo) {
          mediaHtml = `
            <div class="post-media-container" style="width:100%; background:#000; display:flex; justify-content:center; align-items:center; border-bottom: 1px solid var(--border-color);">
              <video src="${post.media_url}" class="post-media-video" controls loop muted playsinline style="width:100%; max-height:500px; object-fit:contain; display:block;"></video>
            </div>
          `;
        } else {
          mediaHtml = `
            <div class="post-media-container" style="width:100%; background:#000; display:flex; justify-content:center; align-items:center; border-bottom: 1px solid var(--border-color);">
              <img src="${post.media_url}" class="post-media-image" alt="Post media" style="width:100%; max-height:500px; object-fit:contain; display:block;">
            </div>
          `;
        }
      } else {
        mediaHtml = `
          <div class="post-media-placeholder">
            <i class="fa-solid ${post.visibility === 'reel' ? 'fa-clapperboard' : 'fa-image'}"></i>
            <p>${post.visibility === 'reel' ? 'Reel Video Clip' : 'Feed Photo Capture'}</p>
            ${post.visibility === 'reel' ? `
              <div class="post-reel-badge">
                <i class="fa-solid fa-play"></i> 15s duration
              </div>
            ` : ''}
          </div>
        `;
      }

      card.innerHTML = `
        <div class="post-header">
          <div class="post-creator-info">
            <div class="post-avatar">${avatarHtml}</div>
            <div class="post-creator-meta">
              <span class="post-username">@${post.username || 'user'}</span>
              <span class="post-location">${post.location || ''}</span>
            </div>
          </div>
          ${post.profile_id === state.profile.profile_id ? `
            <button class="post-action-btn-del" onclick="handleDeletePost(${post.post_id})" title="Delete Post">
              <i class="fa-regular fa-trash-can"></i>
            </button>
          ` : ''}
        </div>
        
        ${mediaHtml}
        
        <div class="post-engagement">
          <div class="post-actions">
            <button class="btn-like ${isLikedByMe ? 'liked' : ''}" onclick="toggleLike(${post.post_id}, ${isLikedByMe})">
              <i class="${isLikedByMe ? 'fa-solid' : 'fa-regular'} fa-heart"></i>
            </button>
            <button onclick="document.getElementById('comment-input-${post.post_id}').focus()"><i class="fa-regular fa-comment"></i></button>
          </div>
          
          <div class="like-count">${likeCount} likes</div>
          
          <div class="post-caption-box">
            <span class="post-caption-username">@${post.username || 'user'}</span>
            <span class="post-caption-text">${post.caption || ''}</span>
          </div>
          
          <div class="post-comments-container">
            ${comments.map(c => `
              <div class="comment-row">
                <span class="comment-username">@${c.username || 'commenter'}</span>
                <span class="comment-text">${c.comment_text}</span>
              </div>
            `).join("")}
          </div>
          
          <form class="comment-input-area" onsubmit="handleCommentSubmit(event, ${post.post_id})">
            <input type="text" id="comment-input-${post.post_id}" placeholder="Add a comment..." required autocomplete="off">
            <button type="submit" class="btn-post-comment">Post</button>
          </form>
        </div>
      `;
      postsContainer.appendChild(card);
    }
  } catch (err) {}
}

async function handleDeletePost(postId) {
  if (!confirm("Are you sure you want to delete this post?")) return;
  try {
    await apiRequest(`/api/posts/${postId}`, "DELETE");
    fetchFeed();
  } catch (err) {}
}

async function toggleLike(postId, alreadyLiked) {
  try {
    if (alreadyLiked) {
      await apiRequest("/api/likes", "DELETE", { target_id: postId, target_type: "post" });
    } else {
      await apiRequest("/api/likes", "POST", { target_id: postId, target_type: "post" });
    }
    fetchFeed();
  } catch (err) {}
}

async function handleCommentSubmit(event, postId) {
  event.preventDefault();
  const input = document.getElementById(`comment-input-${postId}`);
  const text = input.value.trim();
  if (!text) return;
  
  try {
    await apiRequest(`/api/posts/${postId}/comments`, "POST", { comment_text: text });
    input.value = "";
    fetchFeed();
  } catch (err) {}
}

// ==========================================
// STORIES SLIDER SYSTEMS
// ==========================================
async function fetchStories() {
  const tray = document.getElementById("stories-tray");
  
  // Clear dynamic elements, preserve add button
  const createBtn = document.getElementById("btn-create-story");
  tray.innerHTML = "";
  tray.appendChild(createBtn);
  
  try {
    const stories = await apiRequest("/api/stories/active");
    if (stories.length === 0) return;
    
    // Group active stories by user profile username
    const grouped = {};
    for (const story of stories) {
      if (!grouped[story.username]) {
        grouped[story.username] = [];
      }
      grouped[story.username].push(story);
    }
    
    // Render stories groups
    for (const username in grouped) {
      const userStories = grouped[username];
      const latestStory = userStories[0];
      
      const item = document.createElement("div");
      item.className = "story-item";
      item.innerHTML = `
        <div class="story-avatar-container" onclick="openStoryViewer('${username}', ${JSON.stringify(userStories).replace(/"/g, '&quot;')})">
          <div class="story-ring-active"></div>
          <div class="story-avatar">${username.substring(0,2).toUpperCase()}</div>
        </div>
        <span class="story-username">@${username}</span>
      `;
      tray.appendChild(item);
    }
  } catch (err) {}
}

async function openStoryViewer(username, userStories) {
  const modal = document.getElementById("modal-story-viewer");
  modal.classList.remove("hidden");
  
  document.getElementById("story-creator-username").textContent = `@${username}`;
  document.getElementById("story-creator-avatar").textContent = username.substring(0,2).toUpperCase();
  
  const activeStory = userStories[0]; // Renders the latest story first
  
  // Time conversions
  const expiresAt = new Date(activeStory.expires_at);
  const diffHours = Math.ceil((expiresAt - new Date()) / (1000 * 60 * 60));
  document.getElementById("story-expires-timer").textContent = `${diffHours} hours`;
  
  // Mark Viewed in backend
  try {
    await apiRequest(`/api/stories/${activeStory.story_id}/view`, "POST");
  } catch (err) {}

  // Animate Story view bar progress
  const progressFill = document.getElementById("story-progress-fill");
  progressFill.style.width = "0%";
  
  let percentage = 0;
  clearInterval(state.storyTimer);
  state.storyTimer = setInterval(() => {
    percentage += 2;
    progressFill.style.width = `${percentage}%`;
    if (percentage >= 100) {
      closeStoryViewer();
    }
  }, 100);
}

function closeStoryViewer() {
  document.getElementById("modal-story-viewer").classList.add("hidden");
  clearInterval(state.storyTimer);
}

// ==========================================
// DIRECT MESSAGES (CHAT CLIENT)
// ==========================================
async function fetchConversations() {
  const container = document.getElementById("conv-items");
  if (!container.querySelector(".conv-item")) {
    container.innerHTML = `<div class="story-expires-indicator"><i class="fa-solid fa-spinner fa-spin"></i> Loading Chats...</div>`;
  }
  
  try {
    const list = await apiRequest("/api/conversations");
    
    if (list.length === 0) {
      container.innerHTML = `<div class="story-expires-indicator">No active chats. Click the icon to start one!</div>`;
      return;
    }
    
    const items = [];
    for (const conv of list) {
      const isGroup = conv.conversation_type === "group";
      const partner = conv.recipient_username;
      const avatarUrl = conv.recipient_avatar;
      const lastMsg = conv.last_message || "Click to open chat history";
      const displayName = isGroup ? (conv.name || "Group Chat") : `@${partner}`;
      
      const item = document.createElement("div");
      item.className = `conv-item ${sameId(state.activeConversationId, conv.conversation_id) ? 'active' : ''}`;
      item.setAttribute("data-conv-id", conv.conversation_id);
      item.onclick = () => openChatRoom(conv.conversation_id, partner, avatarUrl, isGroup, conv.name);
      
      let avatarHtml = "";
      if (isGroup) {
        avatarHtml = `<div class="conv-avatar group"><i class="fa-solid fa-users"></i></div>`;
      } else {
        avatarHtml = `<div class="conv-avatar">${partner.substring(0, 2).toUpperCase()}</div>`;
        if (avatarUrl) {
          avatarHtml = `<div class="conv-avatar" style="background-image: url('${avatarUrl}'); background-size: cover; background-position: center; color: transparent;"></div>`;
        }
      }

      item.innerHTML = `
        ${avatarHtml}
        <div class="conv-meta">
          <span class="conv-partner">${displayName}</span>
          <span class="conv-lastmsg">${lastMsg}</span>
        </div>
      `;
      items.push(item);
    }
    
    container.innerHTML = "";
    for (const item of items) {
      container.appendChild(item);
    }
  } catch (err) {}
}

function openChatRoom(conversationId, partnerUsername, partnerAvatar = null, isGroup = false, groupName = "") {
  state.activeConversationId = conversationId;
  state.activeConversationPartner = isGroup ? null : partnerUsername;
  state.activeConversationIsGroup = isGroup;
  state.activeConversationGroupName = groupName;

  const chatWindow = document.getElementById("chat-window");
  chatWindow.classList.remove("empty");
  chatWindow.querySelector(".chat-active-state").classList.remove("hidden");
  chatWindow.querySelector(".chat-empty-state").classList.add("hidden");

  const partnerNameEl   = document.getElementById("chat-partner-name");
  const partnerHandleEl = document.getElementById("chat-partner-handle");
  const partnerAvatarEl = document.getElementById("chat-partner-avatar");
  const profileLink     = document.getElementById("chat-partner-profile-link");
  const infoBtn         = document.getElementById("btn-chat-view-profile");

  if (isGroup) {
    const label = groupName || "Group Chat";
    partnerNameEl.textContent   = label;
    partnerHandleEl.textContent = `${(groupName ? groupName.toLowerCase().replace(/\s+/g, "_") : "group")}`;
    partnerAvatarEl.innerHTML   = `<i class="fa-solid fa-users"></i>`;
    partnerAvatarEl.style.background = "linear-gradient(135deg, #12c2e9, #c471ed, #f64f59)";
    // Groups: info button is cosmetic only
    if (infoBtn) infoBtn.onclick = null;
    if (profileLink) profileLink.style.cursor = "default";
  } else {
    partnerNameEl.textContent   = partnerUsername;
    partnerHandleEl.textContent = `@${partnerUsername}`;

    if (partnerAvatar) {
      partnerAvatarEl.innerHTML = `<img src="${partnerAvatar}" alt="Avatar" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
      partnerAvatarEl.style.background = "none";
    } else {
      partnerAvatarEl.innerHTML  = partnerUsername.substring(0, 2).toUpperCase();
      partnerAvatarEl.style.background = "var(--gradient-rainbow)";
    }

    // Clicking the header row or info button navigates to the partner's profile
    const goToProfile = () => {
      state.viewingUsername = partnerUsername;
      switchTab("profile");
    };
    if (profileLink) profileLink.onclick = goToProfile;
    if (infoBtn)     infoBtn.onclick     = goToProfile;
    if (profileLink) profileLink.style.cursor = "pointer";
  }

  // Highlight the selected conversation in the sidebar
  // Use string comparison to avoid large-integer precision issues
  document.querySelectorAll(".conv-item").forEach(item => {
    const convId = item.getAttribute("data-conv-id");
    item.classList.toggle("active", sameId(convId, conversationId));
  });

  fetchChatHistory(conversationId);
}

async function fetchChatHistory(conversationId) {
  if (state.activeConversationId !== conversationId) return;
  
  const msgsContainer = document.getElementById("chat-messages-container");
  try {
    const history = await apiRequest(`/api/conversations/${conversationId}/messages`);
    msgsContainer.innerHTML = "";
    
    if (history.length === 0) {
      msgsContainer.innerHTML = `<div class="story-expires-indicator">No messages yet. Say hello!</div>`;
      return;
    }
    
    for (const msg of history) {
      // Use string comparison to avoid 2^53 large-integer precision loss
      const isOutgoing = state.profile && sameId(msg.sender_id, state.profile.profile_id);
      const reactionString = msg.emoji_reaction || "";
      
      const wrapper = document.createElement("div");
      wrapper.className = `msg-wrapper ${isOutgoing ? 'outgoing' : 'incoming'}`;
      wrapper.setAttribute("data-message-id", msg.message_id);

      let senderLabelHtml = "";
      if (!isOutgoing && state.activeConversationIsGroup) {
        const senderName = msg.sender_username || `user_${msg.sender_id}`;
        senderLabelHtml = `<div class="msg-sender-label">@${senderName}</div>`;
      }

      wrapper.innerHTML = `
        ${senderLabelHtml}
        <div class="msg-bubble">
          ${msg.content}
          ${reactionString ? `<div class="reactions-box">${reactionString}</div>` : ''}
        </div>
        
        <!-- Emoji trigger -->
        ${!isOutgoing ? `
          <button class="reaction-trigger-btn" onclick="reactToMessage(${msg.message_id}, '❤️')" title="React ❤️">
            <i class="fa-regular fa-heart"></i>
          </button>
        ` : ''}
      `;
      msgsContainer.appendChild(wrapper);
      
      if (!isOutgoing) {
        triggerMarkSeen(msg.message_id);
      }
    }
    
    msgsContainer.scrollTop = msgsContainer.scrollHeight;
  } catch (err) {
    console.error("fetchChatHistory error:", err);
    msgsContainer.innerHTML = `<div class="story-expires-indicator" style="color:#e74c3c;">Failed to load messages. Please try again.</div>`;
  }
}

async function triggerMarkSeen(messageId) {
  try {
    await fetch(`/api/messages/${messageId}/seen`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${state.token}` }
    });
  } catch (err) {}
}

async function reactToMessage(messageId, emoji) {
  try {
    await apiRequest(`/api/messages/${messageId}/react`, "POST", { emoji });
    // Refresh history
    fetchChatHistory(state.activeConversationId);
  } catch (err) {}
}

// ==========================================
// PROFILE VIEW GENERATION
// ==========================================
async function fetchProfilePage(targetUsername = null) {
  if (!state.profile) return;
  
  const isOwnProfile = !targetUsername || (state.profile && targetUsername === state.profile.username);
  const username = isOwnProfile ? state.profile.username : targetUsername;
  
  let targetProfile = null;
  if (isOwnProfile) {
    targetProfile = state.profile;
  } else {
    try {
      targetProfile = await apiRequest(`/api/profiles/${username}`);
    } catch (err) {
      showToast("Failed to load user profile");
      return;
    }
  }

  // 1. Populate details
  document.getElementById("profile-page-username").textContent = `@${targetProfile.username}`;
  const avatarEl = document.getElementById("profile-page-avatar");
  if (targetProfile.profile_picture) {
    avatarEl.innerHTML = `<img src="${targetProfile.profile_picture}" alt="Profile picture" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
  } else {
    avatarEl.textContent = targetProfile.username.substring(0, 2).toUpperCase();
  }
  document.getElementById("profile-page-fullname").textContent = targetProfile.full_name || "No Display Name";
  document.getElementById("profile-page-bio").textContent = targetProfile.bio || "No bio yet.";
  
  // Toggle buttons (Edit Profile vs Follow/Unfollow / Message)
  const editBtn = document.getElementById("profile-btn-edit");
  const followBtn = document.getElementById("profile-btn-follow");
  const messageBtn = document.getElementById("profile-btn-message");
  
  if (isOwnProfile) {
    editBtn.classList.remove("hidden");
    followBtn.classList.add("hidden");
    messageBtn.classList.add("hidden");
  } else {
    editBtn.classList.add("hidden");
    followBtn.classList.remove("hidden");
    messageBtn.classList.remove("hidden");

    // Set message button click handler
    const newMessageBtn = messageBtn.cloneNode(true);
    messageBtn.parentNode.replaceChild(newMessageBtn, messageBtn);
    newMessageBtn.addEventListener("click", async () => {
      try {
        const conv = await apiRequest(`/api/conversations?recipient_username=${username}`, "POST");
        switchTab("messages");
        openChatRoom(conv.conversation_id, username, targetProfile.profile_picture);
      } catch (err) {
        showToast("Failed to start message conversation");
      }
    });
  }

  // Avatar hover edit cursor & overlay indicator
  const avatarWrapper = document.getElementById("profile-avatar-wrapper");
  if (isOwnProfile) {
    avatarWrapper.style.cursor = "pointer";
    avatarWrapper.setAttribute("title", "Change Profile Details");
    avatarWrapper.querySelector(".profile-avatar-hover-overlay").style.display = "flex";
  } else {
    avatarWrapper.style.cursor = "default";
    avatarWrapper.removeAttribute("title");
    avatarWrapper.querySelector(".profile-avatar-hover-overlay").style.display = "none";
  }
  
  // Fetch followers and following list to get counts
  let followers = [];
  let following = [];
  try {
    followers = await apiRequest(`/api/${username}/followers`);
    following = await apiRequest(`/api/${username}/following`);
  } catch (e) {}
  
  document.getElementById("profile-followers-count").textContent = followers.length;
  document.getElementById("profile-following-count").textContent = following.length;

  // If it's someone else's profile, update the follow button state
  if (!isOwnProfile) {
    const isFollowing = followers.some(f => f.username === state.profile.username);
    if (isFollowing) {
      followBtn.textContent = "Following";
      followBtn.className = "btn btn-following-user";
    } else {
      followBtn.textContent = "Follow";
      followBtn.className = "btn btn-follow-user";
    }
    
    // Set follow button click handler
    const newFollowBtn = followBtn.cloneNode(true);
    followBtn.parentNode.replaceChild(newFollowBtn, followBtn);
    
    newFollowBtn.addEventListener("click", async () => {
      try {
        if (isFollowing) {
          await apiRequest(`/api/unfollow/${username}`, "POST");
          showToast("Unfollowed successfully", "success");
        } else {
          const res = await apiRequest(`/api/follow/${username}`, "POST");
          if (res.status === "pending") {
            showToast("Follow request sent", "success");
          } else {
            showToast("Followed successfully", "success");
          }
        }
        // Refresh the profile page
        fetchProfilePage(username);
      } catch (err) {
        showToast("Action failed");
      }
    });
  }

  const websiteEl = document.getElementById("profile-page-website");
  if (targetProfile.website) {
    websiteEl.href = targetProfile.website;
    websiteEl.innerHTML = `<i class="fa-solid fa-link"></i> ${targetProfile.website.replace(/(^\w+:|^)\/\//, "")}`;
    websiteEl.style.display = "flex";
  } else {
    websiteEl.style.display = "none";
  }

  // 2. Fetch posts
  const grid = document.getElementById("profile-posts-grid");
  grid.innerHTML = `<div class="story-expires-indicator" style="grid-column: span 3;"><i class="fa-solid fa-spinner fa-spin"></i> Loading posts...</div>`;
  
  try {
    const posts = await apiRequest(`/api/profiles/${username}/posts`);
    grid.innerHTML = "";
    document.getElementById("profile-posts-count").textContent = posts.length;
    
    if (posts.length === 0) {
      grid.innerHTML = `<div class="story-expires-indicator" style="grid-column: span 3; padding: 40px 0;">No posts published yet.</div>`;
    } else {
      for (const post of posts) {
        // Get likes count
        let likes = [];
        try {
          likes = await apiRequest(`/api/likes?target_id=${post.post_id}&target_type=post`);
        } catch (e) {}
        
        // Get comments count
        let comments = [];
        try {
          comments = await apiRequest(`/api/posts/${post.post_id}/comments`);
        } catch (e) {}
        
        let mediaContent = '';
        if (post.media_url) {
          const isVideo = post.media_url.match(/\.(mp4|webm|ogg|mov|m4v)$/i) || post.visibility === 'reel';
          if (isVideo) {
            mediaContent = `<video src="${post.media_url}" style="width: 100%; height: 100%; object-fit: cover; position: absolute; top: 0; left: 0; z-index: 1;" muted></video>
                            <i class="fa-solid fa-clapperboard" style="position: absolute; top: 10px; right: 10px; font-size: 1.1rem; z-index: 2; color: #fff; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));"></i>`;
          } else {
            mediaContent = `<img src="${post.media_url}" style="width: 100%; height: 100%; object-fit: cover; position: absolute; top: 0; left: 0; z-index: 1;">`;
          }
        } else {
          mediaContent = `<i class="fa-solid ${post.visibility === "reel" ? "fa-clapperboard" : "fa-image"}" style="position: relative; z-index: 1;"></i>`;
        }

        const item = document.createElement("div");
        item.className = "grid-post-item";
        item.innerHTML = `
          ${mediaContent}
          <div class="grid-post-overlay" style="z-index: 3;">
            <div class="grid-overlay-item">
              <i class="fa-solid fa-heart"></i> ${likes.length}
            </div>
            <div class="grid-overlay-item">
              <i class="fa-solid fa-comment"></i> ${comments.length}
            </div>
          </div>
        `;
        grid.appendChild(item);
      }
    }
  } catch (err) {
    grid.innerHTML = `<div class="story-expires-indicator" style="grid-column: span 3; color: var(--accent-red);">Failed to load posts.</div>`;
  }

  // 3. Fetch and render user reels
  const reelsGrid = document.getElementById("profile-reels-grid");
  reelsGrid.innerHTML = `<div class="story-expires-indicator" style="grid-column: span 3;"><i class="fa-solid fa-spinner fa-spin"></i> Loading reels...</div>`;
  
  try {
    const reels = await apiRequest(`/api/profiles/${username}/reels`);
    reelsGrid.innerHTML = "";
    
    if (reels.length === 0) {
      reelsGrid.innerHTML = `<div class="story-expires-indicator" style="grid-column: span 3; padding: 40px 0;">No reels published yet.</div>`;
    } else {
      for (const reel of reels) {
        let likes = [];
        try {
          likes = await apiRequest(`/api/likes?target_id=${reel.reel_id}&target_type=reel`);
        } catch (e) {}
        
        let mediaContent = '';
        if (reel.media_url) {
          mediaContent = `<video src="${reel.media_url}" style="width: 100%; height: 100%; object-fit: cover; position: absolute; top: 0; left: 0; z-index: 1;" muted></video>
                          <i class="fa-solid fa-clapperboard" style="position: absolute; top: 10px; right: 10px; font-size: 1.1rem; z-index: 2; color: #fff; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));"></i>`;
        } else {
          mediaContent = `<i class="fa-solid fa-clapperboard" style="position: relative; z-index: 1;"></i>`;
        }

        const item = document.createElement("div");
        item.className = "grid-post-item";
        item.innerHTML = `
          ${mediaContent}
          <div class="grid-post-overlay" style="z-index: 3;">
            <div class="grid-overlay-item">
              <i class="fa-solid fa-heart"></i> ${likes.length}
            </div>
          </div>
        `;
        reelsGrid.appendChild(item);
      }
    }
  } catch (err) {
    reelsGrid.innerHTML = `<div class="story-expires-indicator" style="grid-column: span 3; color: var(--accent-red);">Failed to load reels.</div>`;
  }

  // Default to showing Posts sub-tab
  const btnPosts = document.getElementById("btn-profile-posts");
  if (btnPosts) btnPosts.click();
}

// ==========================================
// RELATIONSHIPS (FOLLOWERS / FOLLOWING) MODAL
// ==========================================
async function showRelationsModal(type) {
  if (!state.profile) return;

  const titleEl = document.getElementById("relations-modal-title");
  const bodyEl = document.getElementById("relations-modal-body");
  const modal = document.getElementById("modal-relations");

  titleEl.textContent = type === "followers" ? "Followers" : "Following";
  bodyEl.innerHTML = `<div class="story-expires-indicator"><i class="fa-solid fa-spinner fa-spin"></i> Loading list...</div>`;
  modal.classList.remove("hidden");

  try {
    const list = await apiRequest(`/api/${state.profile.username}/${type}`);
    bodyEl.innerHTML = "";

    if (list.length === 0) {
      bodyEl.innerHTML = `<div class="story-expires-indicator">No users found.</div>`;
      return;
    }

    for (const u of list) {
      const row = document.createElement("div");
      row.className = "relation-item";
      row.innerHTML = `
        <div class="relation-avatar">${u.username.substring(0, 2).toUpperCase()}</div>
        <div class="relation-details">
          <span class="relation-username">@${u.username}</span>
          <span class="relation-fullname">${u.full_name || ""}</span>
        </div>
      `;
      bodyEl.appendChild(row);
    }
  } catch (err) {
    bodyEl.innerHTML = `<div class="story-expires-indicator" style="color: var(--accent-red);">Failed to load listing.</div>`;
  }
}

// ==========================================
// SEARCH & EXPLORE ACTIONS
// ==========================================
async function performSearch(query) {
  const profilesBox = document.getElementById("search-results-profiles");
  const hashtagsBox = document.getElementById("search-results-hashtags");
  const postsBox = document.getElementById("search-results-posts");
  const reelsBox = document.getElementById("search-results-reels");
  
  profilesBox.innerHTML = "Loading...";
  hashtagsBox.innerHTML = "";
  postsBox.innerHTML = "";
  reelsBox.innerHTML = "";
  
  document.getElementById("search-results-box").classList.remove("hidden");
  document.getElementById("search-explore-box").classList.add("hidden");

  try {
    const results = await apiRequest(`/api/search?q=${encodeURIComponent(query)}`);
    
    profilesBox.innerHTML = "";
    if (results.profiles.length === 0) {
      profilesBox.innerHTML = '<div class="story-expires-indicator">No profiles match.</div>';
    } else {
      results.profiles.forEach(p => {
        const card = document.createElement("div");
        card.className = "search-user-card";
        card.innerHTML = `
          <div class="search-avatar">${p.username.substring(0, 2).toUpperCase()}</div>
          <div class="search-user-info">
            <span class="search-username">@${p.username}</span>
            <span class="search-fullname">${p.full_name || ""}</span>
          </div>
        `;
        card.addEventListener("click", () => {
          if (state.profile && p.username === state.profile.username) {
            state.viewingUsername = null;
          } else {
            state.viewingUsername = p.username;
          }
          switchTab("profile");
        });
        profilesBox.appendChild(card);
      });
    }

    hashtagsBox.innerHTML = "";
    if (results.hashtags.length === 0) {
      hashtagsBox.innerHTML = '<div class="story-expires-indicator">No hashtags match.</div>';
    } else {
      results.hashtags.forEach(h => {
        const tag = document.createElement("span");
        tag.className = "hashtag-tag";
        tag.textContent = `#${h.tag_name} (${h.usage_count})`;
        tag.addEventListener("click", () => {
          document.getElementById("search-input").value = `#${h.tag_name}`;
          performSearch(`#${h.tag_name}`);
        });
        hashtagsBox.appendChild(tag);
      });
    }

    postsBox.innerHTML = "";
    if (results.posts.length === 0) {
      postsBox.innerHTML = '<div class="story-expires-indicator" style="grid-column: span 3;">No posts match.</div>';
    } else {
      results.posts.forEach(post => {
        const item = document.createElement("div");
        item.className = "grid-post-item";
        if (post.media_url) {
          item.innerHTML = `<img src="${post.media_url}" style="width:100%; height:100%; object-fit:cover; position:absolute;">`;
        } else {
          item.innerHTML = `<i class="fa-solid fa-image"></i>`;
        }
        postsBox.appendChild(item);
      });
    }

    reelsBox.innerHTML = "";
    if (results.reels.length === 0) {
      reelsBox.innerHTML = '<div class="story-expires-indicator" style="grid-column: span 3;">No reels match.</div>';
    } else {
      results.reels.forEach(reel => {
        const item = document.createElement("div");
        item.className = "grid-post-item";
        if (reel.media_url) {
          item.innerHTML = `<video src="${reel.media_url}" style="width:100%; height:100%; object-fit:cover; position:absolute;" muted></video>
                            <i class="fa-solid fa-clapperboard" style="position: absolute; top: 10px; right: 10px; z-index: 2; color: #fff;"></i>`;
        } else {
          item.innerHTML = `<i class="fa-solid fa-clapperboard"></i>`;
        }
        item.addEventListener("click", () => {
          switchTab("reels");
        });
        reelsBox.appendChild(item);
      });
    }

  } catch (err) {
    profilesBox.innerHTML = '<div class="story-expires-indicator" style="color: var(--accent-red);">Search failed.</div>';
  }
}

async function fetchExploreGrid() {
  const exploreGrid = document.getElementById("explore-grid");
  exploreGrid.innerHTML = '<div class="story-expires-indicator" style="grid-column: span 3;"><i class="fa-solid fa-spinner fa-spin"></i> Loading Explore...</div>';
  try {
    const feed = await apiRequest("/api/posts/feed");
    exploreGrid.innerHTML = "";
    if (feed.length === 0) {
      exploreGrid.innerHTML = '<div class="story-expires-indicator" style="grid-column: span 3;">No explore items yet. Try creating a post!</div>';
      return;
    }
    feed.forEach(post => {
      const item = document.createElement("div");
      item.className = "grid-post-item";
      if (post.media_url) {
        if (post.media_url.match(/\.(mp4|webm|mov)$/i) || post.visibility === 'reel') {
          item.innerHTML = `<video src="${post.media_url}" style="width:100%; height:100%; object-fit:cover; position:absolute;" muted></video>
                            <i class="fa-solid fa-clapperboard" style="position: absolute; top: 10px; right: 10px; z-index: 2; color: #fff;"></i>`;
        } else {
          item.innerHTML = `<img src="${post.media_url}" style="width:100%; height:100%; object-fit:cover; position:absolute;">`;
        }
      } else {
        item.innerHTML = `<i class="fa-solid fa-image"></i>`;
      }
      exploreGrid.appendChild(item);
    });
  } catch (err) {
    exploreGrid.innerHTML = '<div class="story-expires-indicator" style="grid-column: span 3; color: var(--accent-red);">Failed to load Explore.</div>';
  }
}

// ==========================================
// REELS VERTICAL STREAM LOGIC
// ==========================================
async function fetchReelsFeed() {
  const container = document.getElementById("reels-list-container");
  container.innerHTML = '<div class="story-expires-indicator" style="padding-top: 100px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading Reels...</div>';
  
  try {
    const reels = await apiRequest("/api/reels");
    container.innerHTML = "";
    
    if (reels.length === 0) {
      container.innerHTML = '<div class="story-expires-indicator" style="padding-top: 100px;">No Reels published yet. Create one!</div>';
      return;
    }
    
    await renderReels(reels);
    setupReelsPlaybackIntersection();
  } catch (err) {
    container.innerHTML = '<div class="story-expires-indicator" style="padding-top: 100px; color: var(--accent-red);">Failed to load Reels feed.</div>';
  }
}

async function renderReels(reels) {
  const container = document.getElementById("reels-list-container");
  container.innerHTML = "";
  
  for (const reel of reels) {
    const card = document.createElement("div");
    card.className = "reel-card";
    card.dataset.reelId = reel.reel_id;
    
    let likes = [];
    try {
      likes = await apiRequest(`/api/likes?target_id=${reel.reel_id}&target_type=reel`);
    } catch (e) {}
    
    const isLiked = state.profile && likes.some(l => l.profile_id === state.profile.profile_id);
    
    let comments = [];
    try {
      comments = await apiRequest(`/api/reels/${reel.reel_id}/comments`);
    } catch (e) {}

    let videoContent = "";
    if (reel.media_url) {
      videoContent = `<video src="${reel.media_url}" loop playsinline muted></video>`;
    } else {
      videoContent = `<div class="story-graphic-box" style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%;">
                        <i class="fa-solid fa-clapperboard" style="font-size:3rem;"></i>
                        <p>No Video Content</p>
                      </div>`;
    }
    
    card.innerHTML = `
      <div class="reel-video-container">
        ${videoContent}
        <div class="reel-overlay-info">
          <div class="reel-user-row">
            <div class="reel-avatar">${reel.username.substring(0, 2).toUpperCase()}</div>
            <span class="reel-username">@${reel.username}</span>
            <button class="reel-btn-follow">Follow</button>
          </div>
          <p class="reel-caption">${reel.caption || ""}</p>
        </div>
      </div>
      <div class="reel-actions-column">
        <button class="reel-action-btn btn-like-reel ${isLiked ? 'liked' : ''}" onclick="toggleLikeReel(${reel.reel_id}, this)">
          <i class="fa-solid fa-heart"></i>
          <span class="likes-count">${likes.length}</span>
        </button>
        <button class="reel-action-btn btn-comment-reel" onclick="openReelComments(${reel.reel_id})">
          <i class="fa-solid fa-comment"></i>
          <span>${comments.length}</span>
        </button>
      </div>
    `;
    container.appendChild(card);
  }
}

function setupReelsPlaybackIntersection() {
  const options = {
    root: document.getElementById("reels-list-container"),
    rootMargin: "0px",
    threshold: 0.6
  };
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      const video = entry.target.querySelector("video");
      if (video) {
        if (entry.isIntersecting) {
          video.play().catch(e => console.log("Video auto-play blocked: ", e));
        } else {
          video.pause();
        }
      }
    });
  }, options);
  
  document.querySelectorAll(".reel-card").forEach(card => {
    observer.observe(card);
  });
}

async function toggleLikeReel(reelId, buttonEl) {
  const countEl = buttonEl.querySelector(".likes-count");
  let currentLikes = parseInt(countEl.textContent);
  const isLiked = buttonEl.classList.contains("liked");
  
  try {
    if (isLiked) {
      await apiRequest(`/api/likes?target_id=${reelId}&target_type=reel`, "DELETE");
      buttonEl.classList.remove("liked");
      countEl.textContent = currentLikes - 1;
    } else {
      await apiRequest("/api/likes", "POST", { target_id: reelId, target_type: "reel" });
      buttonEl.classList.add("liked");
      countEl.textContent = currentLikes + 1;
    }
  } catch (err) {
    showToast("Failed to toggle like on reel");
  }
}

async function openReelComments(reelId) {
  const modal = document.getElementById("modal-reel-comments");
  const form = document.getElementById("reel-comment-form");
  form.dataset.reelId = reelId;
  modal.classList.remove("hidden");
  await loadReelComments(reelId);
}

async function loadReelComments(reelId) {
  const listContainer = document.getElementById("reel-comments-list");
  listContainer.innerHTML = '<div class="story-expires-indicator"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</div>';
  
  try {
    const comments = await apiRequest(`/api/reels/${reelId}/comments`);
    listContainer.innerHTML = "";
    
    if (comments.length === 0) {
      listContainer.innerHTML = '<div class="story-expires-indicator">No comments yet. Be the first!</div>';
      return;
    }
    
    comments.forEach(c => {
      const row = document.createElement("div");
      row.className = "relation-item";
      row.innerHTML = `
        <div class="relation-avatar">${c.username ? c.username.substring(0, 2).toUpperCase() : 'U'}</div>
        <div class="relation-details">
          <span class="relation-username" style="font-size:0.85rem;">@${c.username || 'user'}</span>
          <span class="relation-fullname" style="font-size:0.85rem; color:#efefef; margin-top:2px;">${c.comment_text}</span>
        </div>
      `;
      listContainer.appendChild(row);
    });
  } catch (err) {
    listContainer.innerHTML = '<div class="story-expires-indicator" style="color:var(--accent-red);">Failed to load comments.</div>';
  }
}
