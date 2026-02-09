const BASE_URL = "https://wattcoin-production-81a7.up.railway.app";

async function getSolutions() {
  try {
    const response = await fetch(`${BASE_URL}/solutions`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    console.log(data);
  } catch (error) {
    console.error("Error fetching solutions:", error);
  }
}

getSolutions();
