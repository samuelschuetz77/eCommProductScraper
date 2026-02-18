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
    expandedRows = new Set(); 

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
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;900&display=swap" rel="stylesheet">
</svelte:head>

<div class="min-h-screen w-full bg-[#f4f4f5] text-black font-['Inter'] flex flex-col items-center py-12 px-4">
  
  <header class="text-center mb-8" in:fly="{{ y: -10, duration: 400 }}">
    <h1 class="text-4xl font-black tracking-tighter uppercase mb-2">Walmart<br>Extractor</h1>
    <div class="inline-block bg-accent-100 text-accent px-2 py-1 text-xs font-['JetBrains_Mono'] uppercase tracking-widest border border-accent-200">
      v3.1 // 80% Table Mode
    </div>
  </header>

  <div class="w-full max-w-[400px] border-4 border-accent bg-white shadow-accent p-6 mb-16 search-card">
    <form on:submit|preventDefault={scrape} class="flex flex-col gap-5">
      <div>
        <label for="search" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Keyword</label>
        <input type="text" id="search" bind:value={searchTerm} class="w-full bg-gray-100 border-2 border-black p-3 font-bold uppercase rounded-none" placeholder="SEARCH...">
      </div>
      <div class="grid grid-cols-2 gap-4">
        <input type="number" bind:value={minPrice} class="bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] rounded-none" placeholder="MIN $">
        <input type="number" bind:value={maxPrice} class="bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] rounded-none" placeholder="MAX $">
      </div>
      <div>
         <label for="count" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Item Limit</label>
         <input type="number" id="count" bind:value={numProducts} class="w-full bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] rounded-none">
      </div>
      <div class="flex items-center space-x-3 bg-gray-50 p-3 border-2 border-gray-200">
          <input id="manual-solve" type="checkbox" bind:checked={manualSolve} class="w-5 h-5 text-black border-2 border-black rounded-none">
          <label for="manual-solve" class="text-[10px] font-bold uppercase tracking-widest cursor-pointer">Manual Mode</label>
      </div>
      <button type="submit" class="w-full bg-black text-white font-bold py-4 border-2 border-black hover:bg-white hover:text-black transition-all uppercase shadow-accent">
        {loading ? 'PROCESSING...' : 'EXECUTE'}
      </button>
    </form>
  </div>

  <div class="w-[80%] pb-20">
    {#if errorMsg}
        <div class="p-4 border-2 border-red-600 bg-red-50 text-red-600 font-['JetBrains_Mono'] text-sm mb-8 text-center">{errorMsg}</div>
    {/if}

    {#if products.length > 0}
      <div class="border-4 border-black bg-white shadow-[12px_12px_0px_0px_rgba(0,0,0,1)] overflow-hidden" in:fade>
        <table class="w-full border-collapse">
            <thead class="bg-black text-white font-['JetBrains_Mono'] uppercase text-xs">
                <tr>
                    <th class="p-4 w-40 text-center border-r border-white/20">Image</th>
                    <th class="p-4 text-left border-r border-white/20">Product Details</th>
                    <th class="p-4 w-32 text-right border-r border-white/20">Price</th>
                    <th class="p-4 w-32 text-center">Action</th>
                </tr>
            </thead>
            <tbody class="divide-y-4 divide-black">
                {#each products as product, i}
                    <tr class="hover:bg-accent-soft transition-colors">
                        <td class="p-4 align-top border-r border-black/10">
                            <div class="w-32 h-32 border-2 border-black bg-white flex items-center justify-center p-2 mx-auto">
                                {#if product.image}
                                    <img src={product.image} alt="thumb" class="max-w-full max-h-full object-contain">
                                {:else}
                                    <span class="text-[10px] text-gray-400 font-mono">NO_DATA</span>
                                {/if}
                            </div>
                        </td>

                        <td class="p-4 align-top border-r border-black/10">
                            <h3 class="font-black text-lg uppercase leading-none mb-2">{product.name || 'UNKNOWN ITEM'}</h3>
                            <a href={product.link} target="_blank" class="text-[11px] text-accent font-mono break-all opacity-80 hover:opacity-100">{product.link || '#'}</a>
                            
                            {#if expandedRows.has(i)}
                                <div transition:slide class="mt-4 p-4 bg-accent-soft border-2 border-accent-100 font-['JetBrains_Mono'] text-xs">
                                    <p class="mb-2"><span class="bg-black text-white px-1 mr-2">DESC</span>{product.description || 'No extended description found for this record.'}</p>
                                    <p><span class="bg-black text-white px-1 mr-2">SOURCE</span>{product.source || 'DOM_SCAN'}</p>
                                </div>
                            {/if}
                        </td>

                        <td class="p-4 align-top text-right font-['JetBrains_Mono'] font-bold text-2xl border-r border-black/10">
                            ${product.price || '---'}
                        </td>

                        <td class="p-4 align-top text-center">
                            <button on:click={() => toggleDetails(i)} class="w-full bg-black text-white text-[10px] font-bold uppercase py-2 hover:bg-white hover:text-black border-2 border-black transition-all mb-2">
                                {expandedRows.has(i) ? 'CLOSE' : 'DETAILS'}
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