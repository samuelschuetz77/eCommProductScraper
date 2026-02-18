<script>
  import { fade, fly, slide } from 'svelte/transition';

  let searchTerm = '';
  let minPrice = '';
  let maxPrice = '';
  let numProducts = 5;
  let products = [];
  let loading = false;
  let manualSolve = false;
  let errorMsg = '';
  
  // Track which rows are expanded (by index)
  let expandedRows = new Set();

  function toggleDetails(index) {
    if (expandedRows.has(index)) {
        expandedRows.delete(index);
    } else {
        expandedRows.add(index);
    }
    expandedRows = expandedRows; // Trigger reactivity
  }

  async function scrape() {
    loading = true;
    errorMsg = '';
    products = [];
    expandedRows = new Set(); // Reset expansions on new search

    const formData = new FormData();
    formData.append('searchTerm', searchTerm);
    formData.append('minPrice', minPrice);
    formData.append('maxPrice', maxPrice);
    formData.append('numProducts', numProducts);

    try {
      let url = 'http://127.0.0.1:5000/scrape';
      if (manualSolve) {
        url = 'http://127.0.0.1:5000/captcha/interactive';
      }

      const response = await fetch(url, { method: 'POST', body: formData });
      const data = await response.json();

      if (data.error) throw new Error(data.error);
      products = data.products || data;
    } catch (error) {
      console.error('Error:', error);
      errorMsg = error.message || 'Backend unreachable.';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;600;900&display=swap" rel="stylesheet">
</svelte:head>

<div class="min-h-screen w-full bg-[#f4f4f5] text-black font-['Inter'] flex flex-col items-center py-12 px-4">
  
  <header class="text-center mb-8" in:fly="{{ y: -10, duration: 400 }}">
    <h1 class="text-4xl font-black tracking-tighter uppercase mb-2">Walmart<br>Extractor</h1>
    <div class="inline-block bg-black text-white px-2 py-1 text-xs font-['JetBrains_Mono'] uppercase tracking-widest">
      v2.2 // Strict Mode
    </div>
  </header>

  <div class="w-full max-w-[400px] border-4 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] relative z-10 box-border">
    <form on:submit|preventDefault={scrape} class="flex flex-col p-6 gap-5 w-full">
      
      <div class="w-full">
        <label for="search" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Target Keyword</label>
        <input 
          type="text" 
          id="search" 
          bind:value={searchTerm} 
          placeholder="ENTER QUERY..." 
          class="w-full bg-gray-100 border-2 border-black p-3 text-base font-bold uppercase placeholder-gray-400 focus:outline-none focus:bg-yellow-50 focus:border-black transition-colors rounded-none box-border"
        >
      </div>

      <div class="grid grid-cols-2 gap-4 w-full">
        <div>
          <label for="min" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Min $</label>
          <input type="number" id="min" bind:value={minPrice} class="w-full bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] focus:outline-none focus:bg-yellow-50 rounded-none box-border" placeholder="0">
        </div>
        <div>
          <label for="max" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Max $</label>
          <input type="number" id="max" bind:value={maxPrice} class="w-full bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] focus:outline-none focus:bg-yellow-50 rounded-none box-border" placeholder="INF">
        </div>
      </div>

      <div class="w-full">
         <label for="count" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Item Limit</label>
         <input 
            type="number" 
            id="count" 
            bind:value={numProducts} 
            min="1" 
            max="100" 
            class="w-full bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] focus:outline-none focus:bg-yellow-50 rounded-none box-border"
         >
      </div>
      
      <div class="flex items-center space-x-3 bg-gray-50 p-3 border-2 border-gray-200 w-full box-border">
          <input id="manual-solve" type="checkbox" bind:checked={manualSolve} class="w-5 h-5 text-black border-2 border-black rounded-none focus:ring-0 focus:ring-offset-0 cursor-pointer">
          <label for="manual-solve" class="text-[10px] font-bold uppercase tracking-widest cursor-pointer select-none">Manual Mode (Headed)</label>
      </div>

      <button type="submit" disabled={loading} class="w-full bg-black text-white font-bold text-lg py-4 border-2 border-black hover:bg-white hover:text-black hover:shadow-none shadow-[4px_4px_0px_0px_rgba(0,0,0,0.2)] transition-all duration-100 uppercase tracking-wider mt-2">
        {#if loading}
          PROCESSING...
        {:else}
          EXECUTE
        {/if}
      </button>

    </form>
  </div>

  <div class="w-full max-w-5xl mt-16 pb-20">
    {#if errorMsg}
        <div class="p-4 border-2 border-red-600 bg-red-50 text-red-600 font-['JetBrains_Mono'] text-sm mb-8 text-center" in:fade>
            ERROR: {errorMsg}
        </div>
    {/if}

    {#if products.length > 0}
      <div class="border-2 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] overflow-hidden" in:fade>
        <table class="w-full border-collapse text-left">
            <thead class="bg-black text-white font-['JetBrains_Mono'] uppercase text-xs tracking-wider">
                <tr>
                    <th class="p-4 border-b-2 border-black w-24 text-center">Img</th>
                    <th class="p-4 border-b-2 border-black">Product Data</th>
                    <th class="p-4 border-b-2 border-black w-32 text-right">Price</th>
                    <th class="p-4 border-b-2 border-black w-32 text-center">Action</th>
                </tr>
            </thead>
            <tbody class="divide-y-2 divide-gray-100">
                {#each products as product, i}
                    <tr class="hover:bg-gray-50 transition-colors group">
                        <td class="p-4 align-top">
                            <div class="w-16 h-16 border border-gray-200 bg-white flex items-center justify-center p-1 overflow-hidden">
                                {#if product.image}
                                    <img src={product.image} alt="thumbnail" class="max-w-full max-h-full object-contain">
                                {:else}
                                    <span class="text-[8px] text-gray-400 font-mono">N/A</span>
                                {/if}
                            </div>
                        </td>

                        <td class="p-4 align-top">
                            <h3 class="font-bold text-sm uppercase leading-tight mb-1">{product.name || 'UNKNOWN ITEM'}</h3>
                            <a href={product.link} target="_blank" class="text-[10px] text-blue-600 hover:underline font-mono truncate block max-w-md">
                                {product.link || '#'}
                            </a>
                            {#if expandedRows.has(i)}
                                <div transition:slide={{ duration: 200 }} class="mt-4 p-4 bg-gray-100 border-l-4 border-black text-xs font-mono text-gray-600">
                                    <p class="mb-2"><strong class="text-black">SOURCE:</strong> {product.source || 'Scraper'}</p>
                                    <p><strong class="text-black">DESCRIPTION:</strong> {product.description || 'No detailed description available in this record.'}</p>
                                </div>
                            {/if}
                        </td>

                        <td class="p-4 align-top text-right font-['JetBrains_Mono'] font-bold text-lg">
                            ${product.price || '---'}
                        </td>

                        <td class="p-4 align-top text-center">
                            <button 
                                on:click={() => toggleDetails(i)} 
                                class="text-[10px] uppercase font-bold tracking-widest border-2 border-black px-3 py-1 hover:bg-black hover:text-white transition-all w-full mb-2"
                            >
                                {expandedRows.has(i) ? 'Close' : 'Details'}
                            </button>
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>
      </div>
    {/if}
  </div>
</div>