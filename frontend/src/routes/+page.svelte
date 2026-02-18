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
      // Direct backend call
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
      errorMsg = error.message || 'Connection Refused: Check Backend.';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
</svelte:head>

<div class="min-h-screen w-full bg-[#f4f4f5] text-black font-['Inter'] p-8 flex flex-col items-center">
  
  <header class="w-full max-w-6xl grid grid-cols-1 md:grid-cols-2 gap-8 mb-16 border-b-4 border-black pb-8" in:fly="{{ y: -10, duration: 400 }}">
    <div>
      <h1 class="text-6xl font-black tracking-tighter uppercase leading-none mb-2">Walmart<br>Extractor</h1>
      <div class="inline-block bg-black text-white px-2 py-1 text-xs font-['JetBrains_Mono'] uppercase tracking-widest">
        v2.0 // Precision Mode
      </div>
    </div>
    <div class="flex flex-col justify-end items-start md:items-end">
      <p class="text-sm font-['JetBrains_Mono'] text-gray-500 text-right">
        SYSTEM STATUS: <span class="text-green-600 font-bold">READY</span><br>
        TARGET: WALMART_API<br>
        PROTOCOL: NEXT_DATA_JSON
      </p>
    </div>
  </header>

  <div class="w-full max-w-6xl mb-16">
    <form on:submit|preventDefault={scrape} class="grid grid-cols-1 lg:grid-cols-12 gap-0 border-4 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
      
      <div class="lg:col-span-8 p-8 border-b-4 lg:border-b-0 lg:border-r-4 border-black">
        <label for="search" class="block text-xs font-bold uppercase tracking-widest mb-2 font-['JetBrains_Mono']">Query Parameter</label>
        <input 
          type="text" 
          id="search" 
          bind:value={searchTerm} 
          placeholder="ENTER PRODUCT KEYWORD..." 
          class="w-full bg-gray-100 border-2 border-black p-4 text-xl font-bold uppercase placeholder-gray-400 focus:outline-none focus:bg-yellow-50 focus:border-black transition-colors rounded-none"
        >
        
        <div class="grid grid-cols-2 gap-4 mt-6">
          <div>
            <label for="min" class="block text-xs font-bold uppercase tracking-widest mb-2 font-['JetBrains_Mono']">Min Price ($)</label>
            <input type="number" id="min" bind:value={minPrice} class="w-full bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] focus:outline-none focus:bg-yellow-50 rounded-none" placeholder="0">
          </div>
          <div>
            <label for="max" class="block text-xs font-bold uppercase tracking-widest mb-2 font-['JetBrains_Mono']">Max Price ($)</label>
            <input type="number" id="max" bind:value={maxPrice} class="w-full bg-gray-100 border-2 border-black p-3 font-['JetBrains_Mono'] focus:outline-none focus:bg-yellow-50 rounded-none" placeholder="INF">
          </div>
        </div>
      </div>

      <div class="lg:col-span-4 bg-gray-50 p-8 flex flex-col justify-between">
        <div>
           <div class="flex justify-between items-center mb-2">
             <label for="count" class="text-xs font-bold uppercase tracking-widest font-['JetBrains_Mono']">Limit</label>
             <span class="font-['JetBrains_Mono'] font-bold">{numProducts}</span>
           </div>
           <input type="range" id="count" bind:value={numProducts} min="1" max="50" class="w-full h-1 bg-gray-300 rounded-none appearance-none cursor-pointer accent-black mb-6">
           
           <div class="flex items-center space-x-3 mb-6">
              <input id="manual-solve" type="checkbox" bind:checked={manualSolve} class="w-5 h-5 text-black border-2 border-black rounded-none focus:ring-0 focus:ring-offset-0">
              <label for="manual-solve" class="text-xs font-bold uppercase tracking-widest cursor-pointer select-none">Manual Mode (Headed)</label>
          </div>
        </div>

        <button type="submit" disabled={loading} class="w-full bg-black text-white font-bold text-lg py-4 border-2 border-black hover:bg-white hover:text-black transition-all duration-0 active:translate-y-1 disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider">
          {#if loading}
            PROCESSING...
          {:else}
            EXECUTE SCRAPE
          {/if}
        </button>
      </div>
    </form>
  </div>

  <div class="w-full max-w-6xl pb-20">
    {#if errorMsg}
        <div class="p-4 border-2 border-red-600 bg-red-50 text-red-600 font-['JetBrains_Mono'] text-sm mb-8" in:fade>
            ERROR: {errorMsg}
        </div>
    {/if}

    {#if products.length > 0}
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8" in:fade>
        {#each products as product}
          <div class="border-2 border-black bg-white p-0 hover:shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] transition-all duration-200 group">
            
            <div class="w-full h-64 bg-white border-b-2 border-black p-6 flex items-center justify-center relative overflow-hidden">
                {#if product.image}
                    <img src={product.image} alt={product.name} class="max-h-full max-w-full object-contain grayscale group-hover:grayscale-0 transition-all duration-300">
                {:else}
                    <div class="text-gray-300 font-['JetBrains_Mono'] text-xs">NO_IMAGE_DATA</div>
                {/if}
                <div class="absolute top-2 right-2 bg-black text-white text-[10px] px-1 font-['JetBrains_Mono']">
                   IMG_SRC: {product.source || 'JSON'}
                </div>
            </div>

            <div class="p-6">
              <h3 class="font-bold text-lg leading-tight mb-4 h-14 line-clamp-2 uppercase">{product.name || 'UNKNOWN ITEM'}</h3>
              
              <div class="grid grid-cols-2 gap-4 border-t-2 border-gray-100 pt-4">
                 <div>
                    <div class="text-[10px] text-gray-500 font-['JetBrains_Mono'] uppercase">Price</div>
                    <div class="text-2xl font-black">${product.price || '---'}</div>
                 </div>
                 <div class="flex items-end justify-end">
                    <a href={product.link} target="_blank" class="text-xs font-bold underline decoration-2 decoration-black hover:bg-black hover:text-white px-2 py-1 transition-colors">
                        VISIT LINK &rarr;
                    </a>
                 </div>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>