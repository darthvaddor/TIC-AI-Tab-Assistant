// Reminder notification popup for webpages
(function() {
  'use strict';
  
  // Prevent duplicate notifications
  if (window.__reminderNotificationInjected) {
    return;
  }
  window.__reminderNotificationInjected = true;
  
  function showReminderNotification(message) {
    // Remove any existing notification
    const existing = document.getElementById('tab-sensei-reminder-notification');
    if (existing) {
      existing.remove();
    }
    
    // Create notification container
    const notification = document.createElement('div');
    notification.id = 'tab-sensei-reminder-notification';
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      width: 320px;
      min-height: 80px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 16px 20px;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      z-index: 2147483647;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      display: flex;
      flex-direction: column;
      gap: 8px;
      animation: slideIn 0.3s ease-out;
      cursor: default;
    `;
    
    // Add animation
    const style = document.createElement('style');
    style.textContent = `
      @keyframes slideIn {
        from {
          transform: translateX(400px);
          opacity: 0;
        }
        to {
          transform: translateX(0);
          opacity: 1;
        }
      }
      #tab-sensei-reminder-notification {
        pointer-events: auto !important;
      }
    `;
    if (!document.getElementById('tab-sensei-reminder-styles')) {
      style.id = 'tab-sensei-reminder-styles';
      document.head.appendChild(style);
    }
    
    // Title
    const title = document.createElement('div');
    title.style.cssText = `
      font-weight: 600;
      font-size: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;
    `;
    title.innerHTML = '⏰ <span>Tab Sensei Reminder</span>';
    
    // Message
    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
      color: rgba(255, 255, 255, 0.95);
      word-wrap: break-word;
    `;
    messageDiv.textContent = message;
    
    // Close button with proper event handling
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '✕';
    closeBtn.setAttribute('type', 'button'); // Prevent form submission
    closeBtn.style.cssText = `
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(255, 255, 255, 0.2);
      border: none;
      color: white;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      cursor: pointer;
      font-size: 18px;
      line-height: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
      padding: 0;
      z-index: 2147483648;
      pointer-events: auto;
      user-select: none;
    `;
    
    // Hover effects
    closeBtn.addEventListener('mouseenter', () => {
      closeBtn.style.background = 'rgba(255, 255, 255, 0.3)';
    });
    closeBtn.addEventListener('mouseleave', () => {
      closeBtn.style.background = 'rgba(255, 255, 255, 0.2)';
    });
    
    // Close handler - use addEventListener for better compatibility
    const closeHandler = (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      console.log('[TabSensei] Close button clicked in content script');
      
      // Remove notification immediately
      if (notification && notification.parentNode) {
        notification.remove();
        console.log('[TabSensei] Notification removed from content script');
      }
      return false;
    };
    
    closeBtn.addEventListener('click', closeHandler, true); // Use capture phase
    closeBtn.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      // Also close on mousedown as backup
      if (notification && notification.parentNode) {
        notification.remove();
      }
    }, true);
    
    // Touch events for mobile
    closeBtn.addEventListener('touchend', closeHandler, true);
    closeBtn.addEventListener('touchstart', (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, true);
    
    // Play notification sound (pleasant two-tone chime)
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      
      // First tone
      const osc1 = audioContext.createOscillator();
      const gain1 = audioContext.createGain();
      osc1.type = 'sine';
      osc1.frequency.value = 800;
      gain1.gain.setValueAtTime(0, audioContext.currentTime);
      gain1.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.05);
      gain1.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.2);
      osc1.connect(gain1);
      gain1.connect(audioContext.destination);
      osc1.start(audioContext.currentTime);
      osc1.stop(audioContext.currentTime + 0.2);
      
      // Second tone (slightly delayed)
      setTimeout(() => {
        try {
          const osc2 = audioContext.createOscillator();
          const gain2 = audioContext.createGain();
          osc2.type = 'sine';
          osc2.frequency.value = 1000;
          gain2.gain.setValueAtTime(0, audioContext.currentTime);
          gain2.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.05);
          gain2.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.2);
          osc2.connect(gain2);
          gain2.connect(audioContext.destination);
          osc2.start(audioContext.currentTime);
          osc2.stop(audioContext.currentTime + 0.2);
        } catch (e) {
          // Ignore errors in second tone
        }
      }, 100);
    } catch (e) {
      // If Web Audio API fails, try a simple beep
      try {
        const beep = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZiTYIG2m98OSdTgwOUKjj8LZjHAY4kdfyzHksBSR3x/DdkEAKFF606euoVRQKRp/g8r5sIQUrgc7y2Yk2CBtpvfDknU4MDlCo4/C2YxwGOJHX8sx5LAUkd8fw3ZBAC');
        beep.volume = 0.3;
        beep.play().catch(() => {
          // If audio fails, that's okay - notification will still show
        });
      } catch (audioError) {
        // Sound is optional - notification will still work
      }
    }
    
    // Assemble
    notification.appendChild(title);
    notification.appendChild(messageDiv);
    notification.appendChild(closeBtn);
    
    // Add to page
    document.body.appendChild(notification);
    
    // Make sure it stays on top
    notification.style.position = 'fixed';
    notification.style.zIndex = '2147483647';
  }
  
  // Listen for messages from background script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'showReminderNotification') {
      showReminderNotification(request.message);
      sendResponse({ success: true });
    }
  });
  
  // Expose function globally for direct calls
  window.showTabSenseiReminder = showReminderNotification;
})();

