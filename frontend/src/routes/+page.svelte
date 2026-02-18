<script>
  import { slide } from 'svelte/transition';

  let searchTerm = '';
  let minPrice = 0;
  let maxPrice = 1000;
  let numProducts = 2;
  let products = [];
  let loading = false;
  let manualSolve = false;

  async function scrape() {
    loading = true;
    products = [];

    const formData = new FormData();
    formData.append('searchTerm', searchTerm);
    formData.append('minPrice', minPrice);
    formData.append('maxPrice', maxPrice);
    formData.append('numProducts', numProducts);

    try {
      let url = '/scrape';
      // if manualSolve is checked use the interactive endpoint which opens a
      // headed browser for manual captcha solving
      if (manualSolve) {
        // call the Flask interactive captcha endpoint directly to avoid proxy issues
        url = 'http://127.0.0.1:5000/captcha/interactive';
      }

      const response = await fetch(url, {
        method: 'POST',
        body: formData,
      });

      const json = await response.json();
      // the interactive endpoint returns { products: [...] } similar to /scrape
      products = json.products || json;
    } catch (error) {
      console.error('Error scraping:', error);
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
</svelte:head>

<div class="bg-gray-100 min-h-screen font-['Poppins'] text-gray-800 p-4 sm:p-6 lg:p-8">
  <div class="max-w-7xl mx-auto">
    <header class="text-center py-12">
      <h1 class="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 tracking-tight">
        Walmart Product Scraper
      </h1>
      <p class="mt-4 max-w-2xl mx-auto text-lg text-gray-600">
        Find the best deals at Walmart, instantly.
      </p>
    </header>

    <div class="max-w-sm mx-auto bg-white p-6 rounded-2xl shadow-lg mt-8">
      <h2 class="text-2xl font-bold mb-6 text-center">Search</h2>
      <form on:submit|preventDefault={scrape}>
        <div class="space-y-6">
          <div>
            <label for="search-term" class="block text-sm font-medium text-gray-700">Search Term</label>
            <div class="mt-1 relative">
              <input type="text" id="search-term" bind:value={searchTerm} class="pl-10 pr-4 py-2 w-full border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition" placeholder="e.g., 'laptop'">
              <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg class="h-5 w-5 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
            </div>
          </div>

          <div>
            <h3 class="text-lg font-medium text-gray-800 mb-4">Filters</h3>
            <div class="space-y-4">
              <div>
                <label for="min-price" class="block text-sm font-medium text-gray-700">Min Price</label>
                <div class="mt-1 relative">
                  <input type="number" id="min-price" bind:value={minPrice} class="pl-10 pr-4 py-2 w-full border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition" placeholder="0">
                  <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <span class="text-gray-500 sm:text-sm">$</span>
                  </div>
                </div>
              </div>
              <div>
                <label for="max-price" class="block text-sm font-medium text-gray-700">Max Price</label>
                <div class="mt-1 relative">
                  <input type="number" id="max-price" bind:value={maxPrice} class="pl-10 pr-4 py-2 w-full border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition" placeholder="1000">
                  <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <span class="text-gray-500 sm:text-sm">$</span>
                  </div>
                </div>
              </div>
              <div>
                <label for="num-products" class="block text-sm font-medium text-gray-700"># of Products</label>
                <input type="number" id="num-products" bind:value={numProducts} class="mt-1 w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500" placeholder="2">
              </div>
              <div class="flex items-center mt-3">
                <input id="manual-solve" type="checkbox" bind:checked={manualSolve} class="h-4 w-4 text-blue-600 border-gray-300 rounded" />
                <label for="manual-solve" class="ml-2 block text-sm text-gray-700">Open headed browser for manual captcha</label>
              </div>
            </div>
          </div>
        </div>
        <div class="mt-8">
          <button type="submit" class="w-full inline-flex items-center justify-center px-6 py-3 border border-transparent text-base font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 shadow-lg transform hover:scale-105 transition-transform duration-300">
            {#if loading}
              <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Searching...
            {:else}
              Search Products
            {/if}
          </button>
        </div>
      </form>
    </div>

    <div class="mt-16 max-w-5xl mx-auto">
      {#if loading}
        <div class="text-center py-24">
          <p class="text-xl text-gray-500">Scraping the web for you...</p>
        </div>
      {:else if products.length > 0}
        <div class="bg-white p-6 rounded-2xl shadow-lg overflow-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-6 py-3 text-left text-sm font-semibold text-gray-700">Name</th>
                <th class="px-6 py-3 text-left text-sm font-semibold text-gray-700">Price</th>
                <th class="px-6 py-3 text-left text-sm font-semibold text-gray-700">Link</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              {#each products as product}
                <tr>
                  <td class="px-6 py-4 text-sm text-gray-900">{product.name}</td>
                  <td class="px-6 py-4 text-sm font-medium text-gray-900">${product.price}</td>
                  <td class="px-6 py-4 text-sm text-blue-600"><a href={product.link} target="_blank" rel="noreferrer">View</a></td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <div class="text-center py-24 bg-white rounded-2xl shadow-lg">
          <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
          </svg>
          <h3 class="mt-2 text-xl font-medium text-gray-900">No products found</h3>
          <p class="mt-1 text-md text-gray-500">Try adjusting your search or filters.</p>
        </div>
      {/if}
    </div>
  </div>
</div>
