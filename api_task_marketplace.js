// api_task_marketplace.js

const axios = require('axios');
const { taskStatus } = require('./constants');

async function verifyAI(taskId, aiApiKey) {
  const maxRetries = 3;
  let retryDelay = 1000;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const response = await axios.post('https://api.example.com/verify', { taskId }, {
        headers: { 'Authorization': `Bearer ${aiApiKey}` },
        timeout: 30000
      });

      if (response.data.success) {
        return true;
      } else {
        console.log(`AI verification failed for task ${taskId}: ${response.data.message}`);
        return false;
      }
    } catch (error) {
      if (error.response && (error.response.status >= 500 || error.response.status === 408)) {
        console.log(`Attempt ${attempt} of ${maxRetries} failed. Retrying in ${retryDelay / 1000}s...`);
        await new Promise(resolve => setTimeout(resolve, retryDelay));
        retryDelay *= 2;
      } else if (error.response) {
        console.log(`Request error: ${error.response.data.message}`);
      } else if (error.request) {
        console.log('No response received');
      } else {
        console.log(`Error making request: ${error.message}`);
      }

      if (attempt === maxRetries) {
        console.log(`All ${maxRetries} attempts failed. Setting task status to 'pending_review'.`);
        await updateTaskStatus(taskId, taskStatus.pending_review);
        return false;
      }
    }
  }
}

async function updateTaskStatus(taskId, newStatus) {
  // Logic to update the task status in the database or other storage system
}
