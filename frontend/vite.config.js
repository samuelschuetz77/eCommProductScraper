import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			'/scrape': 'http://127.0.0.1:5000',
			'/download_csv': 'http://127.0.0.1:5000',
			'/captcha': 'http://127.0.0.1:5000'
		}
	}
});
