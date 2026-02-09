const BASE_URL = "https://wattcoin-production-81a7.up.railway.app";

async function getNodes() {
  try {
    const response = await fetch(`${BASE_URL}/nodes`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    console.log(data);
  } catch (error) {
    console.error("Error fetching nodes:", error);
  }
}

getNodes();
