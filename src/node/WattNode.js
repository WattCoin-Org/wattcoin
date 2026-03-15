// WattNode.js - A script to run the WattNode for 7 days and complete jobs

const { exec } = require('child_process');

class WattNode {
  constructor() {
    this.jobCount = 0;
    this.startTime = Date.now();
  }

  // Start the node process
  startNode() {
    exec('node wattcoin-node.js', (err, stdout, stderr) => {
      if (err) {
        console.error(`Error starting node: ${err}`);
        return;
      }
      console.log(`Node started successfully: ${stdout}`);
      this.monitorNode();
    });
  }

  // Monitor the node to keep it running for 7 days
  monitorNode() {
    const interval = setInterval(() => {
      const currentTime = Date.now();
      if (currentTime - this.startTime >= 7 * 24 * 60 * 60 * 1000) { // 7 days
        clearInterval(interval);
        console.log('7 days have passed, stopping the node.');
        this.stopNode();
      } else {
        this.completeJob();
      }
    }, 60 * 60 * 1000); // Check every hour
  }

  // Simulate completing a job
  completeJob() {
    this.jobCount += 1;
    console.log(`Job ${this.jobCount} completed.`);
    if (this.jobCount >= 50) {
      console.log('Completed 50 jobs, preparing for completion...');
      this.stopNode();
    }
  }

  // Stop the node process
  stopNode() {
    exec('pkill -f wattcoin-node.js', (err, stdout, stderr) => {
      if (err) {
        console.error(`Error stopping node: ${err}`);
        return;
      }
      console.log(`Node stopped successfully: ${stdout}`);
    });
  }
}

// Run the node
const wattNode = new WattNode();
wattNode.startNode();