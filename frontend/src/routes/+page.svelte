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

  /* Removed JS auto-spacer — using CSS sticky panel + responsive spacer instead */

  // ------------------------------------------------------------------------

  async function scrape() {
    loading = true;
    errorMsg = '';
    // Don't clear products immediately to prevent UI flash
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

      // content updated — spacing handled by CSS (sticky + responsive spacer)
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

<div class="min-h-screen w-full bg-[#f4f4f5] text-black font-['Inter'] flex flex-col items-center py-12 px-4 overflow-x-hidden">
  
  <header class="text-center mb-10" in:fly="{{ y: -10, duration: 400 }}">
    <h1 class="text-4xl font-black tracking-tighter uppercase mb-2">Walmart<br>Extractor</h1>
    <div class="inline-block bg-black text-white px-2 py-1 text-xs font-['JetBrains_Mono'] uppercase tracking-widest">
      v3.2 // Ink Mode
    </div>
  </header>

  <div class="w-full max-w-[450px] border-4 border-black bg-white shadow-[8px_8px_0px_0px_#020617] p-6 mb-24 sticky top-6 z-20 box-border">
    
    <form on:submit|preventDefault={scrape} class="flex flex-col gap-5 w-full">
      
      <div class="w-full">
        <label for="search" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Keyword</label>
        <input 
            type="text" 
            id="search" 
            bind:value={searchTerm} 
            class="w-full box-border bg-gray-100 border-2 border-black p-3 font-bold uppercase rounded-none focus:outline-none focus:bg-yellow-50 transition-colors" 
            placeholder="SEARCH..."
        >
      </div>

      <div class="grid grid-cols-2 gap-4 w-full">
        <div class="w-full">
            <label for="min" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Min $</label>
            <input 
                type="number" 
                id="min" 
                bind:value={minPrice} 
                class="w-full box-border bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] rounded-none focus:outline-none focus:bg-yellow-50" 
                placeholder="0"
            >
        </div>
        <div class="w-full">
            <label for="max" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Max $</label>
            <input 
                type="number" 
                id="max" 
                bind:value={maxPrice} 
                class="w-full box-border bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] rounded-none focus:outline-none focus:bg-yellow-50" 
                placeholder="INF"
            >
        </div>
      </div>

      <div class="w-full">
         <label for="count" class="block text-xs font-bold uppercase tracking-widest mb-1 font-['JetBrains_Mono']">Item Limit</label>
         <input 
            type="number" 
            id="count" 
            bind:value={numProducts} 
            class="w-full box-border bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] rounded-none focus:outline-none focus:bg-yellow-50"
         >
      </div>

      <div class="flex items-center space-x-3 bg-gray-50 p-3 border-2 border-gray-200 w-full box-border">
          <input 
            id="manual-solve" 
            type="checkbox" 
            bind:checked={manualSolve} 
            class="w-5 h-5 text-black border-2 border-black rounded-none focus:ring-0 cursor-pointer accent-black"
          >
          <label for="manual-solve" class="text-[10px] font-bold uppercase tracking-widest cursor-pointer select-none">Manual Mode (Headed)</label>
      </div>

      <button 
        type="submit" 
        class="w-full box-border bg-black text-white font-bold py-4 border-2 border-black hover:bg-white hover:text-black transition-all uppercase shadow-[4px_4px_0px_0px_rgba(0,0,0,0.2)] hover:shadow-none hover:translate-x-[2px] hover:translate-y-[2px]"
      >
        {loading ? 'PROCESSING...' : 'EXECUTE'}
      </button>

    </form>
  </div>

  <!-- fixed responsive spacer so sticky panel never overlaps content -->
  <div class="h-6 sm:h-32 md:h-64 lg:h-96" aria-hidden="true"></div>

  <div class="w-[90%] md:w-[80%] pb-20 mt-6 sm:mt-32 md:mt-64 lg:mt-96">
    {#if errorMsg}
        <div class="p-4 border-2 border-red-600 bg-red-50 text-red-600 font-['JetBrains_Mono'] text-sm mb-8 text-center uppercase tracking-wide shadow-[4px_4px_0px_0px_#ef4444]">{errorMsg}</div>
    {/if}

    {#if products.length > 0}
      <div class="border-4 border-black bg-white shadow-[12px_12px_0px_0px_rgba(0,0,0,1)] overflow-hidden" in:fade>
        <table class="w-full border-collapse table-fixed">
            <thead class="bg-black text-white font-['JetBrains_Mono'] uppercase text-xs">
                <tr>
                    <th class="p-4 w-32 md:w-48 text-center border-r border-white/20">Image</th>
                    <th class="p-4 text-left border-r border-white/20 w-auto">Product Details</th>
                    <th class="p-4 w-24 md:w-32 text-right border-r border-white/20">Price</th>
                    <th class="p-4 w-24 md:w-32 text-center">Action</th>
                </tr>
            </thead>
            <tbody class="divide-y-4 divide-black">
                {#each products as product, i}
                    <tr class="hover:bg-yellow-50/50 transition-colors">
                        <td class="p-4 align-top border-r border-black/10">
                            <div class="w-24 h-24 md:w-32 md:h-32 border-2 border-black bg-white flex items-center justify-center p-2 mx-auto shadow-[4px_4px_0px_0px_rgba(0,0,0,0.1)]">
                                {#if product.image}
                                    <img src={product.image} alt="thumb" class="max-w-full max-h-full object-contain grayscale group-hover:grayscale-0 transition-all">
                                {:else}
                                    <span class="text-[10px] text-gray-400 font-mono">NO_DATA</span>
                                {/if}
                            </div>
                        </td>

                        <td class="p-4 align-top border-r border-black/10">
                            <h3 class="font-black text-base md:text-xl uppercase leading-none mb-3 line-clamp-2">{product.name || 'UNKNOWN ITEM'}</h3>
                            
                            <a href={product.link} target="_blank" class="text-[10px] md:text-xs text-blue-700 font-mono break-all opacity-70 hover:opacity-100 hover:underline decoration-2 mb-4 block">
                                {product.link || '#'}
                            </a>
                            
                            {#if expandedRows.has(i)}
                                <div transition:slide class="mt-4 p-4 bg-gray-50 border-2 border-black font-['JetBrains_Mono'] text-xs shadow-[4px_4px_0px_0px_rgba(0,0,0,0.1)]">
                                    <p class="mb-2"><span class="bg-black text-white px-1 mr-2">DESC</span>{product.description || 'No extended description found.'}</p>
                                    <p><span class="bg-black text-white px-1 mr-2">SOURCE</span>{product.source || 'DOM_SCAN'}</p>
                                </div>
                            {/if}
                        </td>

                        <td class="p-4 align-top text-right font-['JetBrains_Mono'] font-bold text-xl md:text-2xl border-r border-black/10">
                            ${product.price || '---'}
                        </td>

                        <td class="p-4 align-top text-center">
                            <button 
                                on:click={() => toggleDetails(i)} 
                                class="w-full bg-white text-black text-[10px] font-bold uppercase py-2 border-2 border-black hover:bg-black hover:text-white transition-all shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none"
                            >
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