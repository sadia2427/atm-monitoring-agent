/**
 * public/js/login.js
 * Handles admin credential submission and login validation.
 */

'use strict';

document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('loginForm');
  const loginError = document.getElementById('loginError');
  const errorMessage = document.getElementById('errorMessage');

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;

    loginError.style.display = 'none';

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      const result = await response.json();

      if (response.ok && result.success) {
        // Save user details to localStorage for UI customizations
        localStorage.setItem('user', JSON.stringify(result.data));
        // Redirect to dashboard
        window.location.href = '/index.html';
      } else {
        errorMessage.textContent = result.error || 'Invalid credentials. Please try again.';
        loginError.style.display = 'flex';
      }
    } catch (err) {
      console.error('[login] Error during authentication request:', err);
      errorMessage.textContent = 'Server connection failed. Please verify the server is running.';
      loginError.style.display = 'flex';
    }
  });
});
