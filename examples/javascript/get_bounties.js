const BASE_URL = "https://wattcoin-production-81a7.up.railway.app";

async function getBounties() {
  try {
    const response = await fetch(`${BASE_URL}/bounties`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    console.log(data);
  } catch (error) {
    console.error("Error fetching bounties:", error);
  }
}

getBounties();
