document.getElementById('search-form').addEventListener('submit', function(event) {
    event.preventDefault();

    const searchTerm = document.getElementById('search-term').value;
    const minPrice = document.getElementById('min-price').value;
    const maxPrice = document.getElementById('max-price').value;

    const productResults = document.getElementById('product-results');
    productResults.innerHTML = '<p>Scraping...</p>';

    const formData = new FormData();
    formData.append('searchTerm', searchTerm);
    formData.append('minPrice', minPrice);
    formData.append('maxPrice', maxPrice);

    fetch('/scrape', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(products => {
        productResults.innerHTML = '';
        if (products.length === 0) {
            productResults.innerHTML = '<p>No products found.</p>';
            return;
        }

        products.forEach(product => {
            const productDiv = document.createElement('div');
            productDiv.classList.add('product');

            const image = document.createElement('img');
            image.src = product.image;
            productDiv.appendChild(image);

            const name = document.createElement('h3');
            name.textContent = product.name;
            productDiv.appendChild(name);

            const price = document.createElement('p');
            price.textContent = `$${product.price}`;
            productDiv.appendChild(price);

            productResults.appendChild(productDiv);
        });

        // Add download button
        const downloadButton = document.createElement('a');
        downloadButton.href = '/download_csv'; // We'll create this route later
        downloadButton.textContent = 'Download as CSV';
        downloadButton.style.display = 'block';
        downloadButton.style.marginTop = '1rem';
        productResults.parentNode.appendChild(downloadButton);

    })
    .catch(error => {
        console.error('Error:', error);
        productResults.innerHTML = '<p>An error occurred. Please try again.</p>';
    });
});
