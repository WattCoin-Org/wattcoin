const BASE_URL = "https://wattcoin-production-81a7.up.railway.app";

async function getStats() {
  try {
    const response = await fetch(`${BASE_URL}/stats`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    console.log(data);
  } catch (error) {
    console.error("Error fetching stats:", error);
  }
}

getStats();
