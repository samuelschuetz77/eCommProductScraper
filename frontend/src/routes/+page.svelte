<script>
  import { fade, fly } from 'svelte/transition';

  let searchTerm = '';
  let minPrice = '';
  let maxPrice = '';
  let numProducts = 5;
  let products = [];
  let loading = false;
  let manualSolve = false;
  let errorMsg = '';

  async function scrape() {
    loading = true;
    errorMsg = '';
    products = [];

    const formData = new FormData();
    formData.append('searchTerm', searchTerm);
    formData.append('minPrice', minPrice);
    formData.append('maxPrice', maxPrice);
    formData.append('numProducts', numProducts);

    try {
      let url = '/scrape';
      if (manualSolve) {
        url = 'http://127.0.0.1:5000/captcha/interactive';
      }

      const response = await fetch(url, { method: 'POST', body: formData });
      const data = await response.json();

      if (data.error) throw new Error(data.error);
      
      products = data.products || data;
    } catch (error) {
      console.error('Error:', error);
      errorMsg = error.message || 'An unknown error occurred.';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
</svelte:head>

<div class="min-h-screen w-full bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 flex flex-col items-center justify-start py-12 px-4 font-['Inter'] selection:bg-indigo-500 selection:text-white">
  
  <header class="text-center mb-10" in:fly="{{ y: -20, duration: 800 }}">
    <h1 class="text-4xl font-light tracking-tight text-slate-800">
      Walmart <span class="font-semibold text-indigo-600">Extract</span>
    </h1>
    <p class="mt-2 text-slate-500 text-sm tracking-wide uppercase">Precision Data Scraper</p>
  </header>

  <div class="w-full max-w-md relative group">
    <div class="absolute -inset-1 bg-gradient-to-r from-indigo-400 to-purple-400 rounded-2xl blur opacity-20 group-hover:opacity-40 transition duration-1000 group-hover:duration-200"></div>
    
    <div class="relative w-full bg-white/70 backdrop-blur-xl border border-white/50 shadow-2xl rounded-2xl p-8 overflow-hidden">
      <div class="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-b from-white/40 to-transparent pointer-events-none"></div>

      <form on:submit|preventDefault={scrape} class="space-y-6 relative z-10">
        
        <div>
          <label for="search" class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Search Query</label>
          <input 
            type="text" 
            id="search" 
            bind:value={searchTerm} 
            placeholder="e.g. Sony WH-1000XM5" 
            class="w-full bg-white/50 border border-slate-200 rounded-lg px-4 py-3 text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-transparent transition-all shadow-sm"
          >
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label for="min" class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Min Price</label>
            <div class="relative">
              <span class="absolute left-3 top-3 text-slate-400">$</span>
              <input type="number" id="min" bind:value={minPrice} class="w-full pl-7 bg-white/50 border border-slate-200 rounded-lg px-4 py-3 text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all shadow-sm" placeholder="0">
            </div>
          </div>
          <div>
            <label for="max" class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Max Price</label>
            <div class="relative">
              <span class="absolute left-3 top-3 text-slate-400">$</span>
              <input type="number" id="max" bind:value={maxPrice} class="w-full pl-7 bg-white/50 border border-slate-200 rounded-lg px-4 py-3 text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all shadow-sm" placeholder="Any">
            </div>
          </div>
        </div>

        <div>
          <label for="count" class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Limit</label>
          <input type="range" id="count" bind:value={numProducts} min="1" max="50" class="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600">
          <div class="text-right text-xs text-slate-500 mt-1">{numProducts} items</div>
        </div>

        <div class="flex items-center space-x-3 bg-indigo-50/50 p-3 rounded-lg border border-indigo-100/50">
            <input id="manual-solve" type="checkbox" bind:checked={manualSolve} class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500">
            <label for="manual-solve" class="text-sm text-slate-600 cursor-pointer select-none">Manual Captcha Mode (Headed)</label>
        </div>

        <button type="submit" disabled={loading} class="w-full bg-slate-900 hover:bg-black text-white font-medium py-3.5 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 transform active:scale-[0.98] disabled:opacity-70 disabled:cursor-not-allowed">
          {#if loading}
            <span class="flex items-center justify-center space-x-2">
                <svg class="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Processing...</span>
            </span>
          {:else}
            Search Walmart
          {/if}
        </button>
      </form>
    </div>
  </div>

  <div class="w-full max-w-4xl mt-16 px-4 pb-20">
    {#if errorMsg}
        <div class="p-4 rounded-xl bg-red-50 text-red-600 border border-red-100 text-center text-sm" in:fade>
            {errorMsg}
        </div>
    {/if}

    {#if products.length > 0}
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6" in:fade>
        {#each products as product}
          <div class="bg-white/80 backdrop-blur-sm border border-white/60 p-4 rounded-xl shadow-sm hover:shadow-md transition-all duration-300 group">
            <div class="aspect-square w-full bg-white rounded-lg overflow-hidden mb-4 relative">
                {#if product.image}
                    <img src={product.image} alt={product.name} class="w-full h-full object-contain mix-blend-multiply group-hover:scale-105 transition duration-500">
                {:else}
                    <div class="flex items-center justify-center h-full text-slate-300 text-xs uppercase">No Image</div>
                {/if}
            </div>
            <h3 class="font-medium text-slate-800 leading-snug line-clamp-2 text-sm mb-2 h-10">{product.name || 'Untitled Product'}</h3>
            <div class="flex items-center justify-between mt-2">
                <span class="text-lg font-bold text-slate-900">${product.price || '---'}</span>
                <a href={product.link} target="_blank" class="text-xs bg-indigo-50 text-indigo-600 px-3 py-1.5 rounded-full font-medium hover:bg-indigo-100 transition-colors">View</a>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>