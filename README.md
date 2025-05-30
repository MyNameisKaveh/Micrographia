# Taxonomy App - Species Classification & Name Suggestion

A simple and engaging web application to search and display taxonomy (classification) information and images of living organisms. It also includes a feature to suggest scientific names based on common names.

**✨ [View Live Demo](https://mynameiskaveh.github.io/taxonomy-app/) ✨**
<!-- Make sure this is your correct GitHub Pages link -->

## 🌟 About The Project

This project was developed as a learning exercise to showcase working with external APIs, building a serverless Python backend, and developing a frontend using HTML, CSS, and JavaScript. Users can:
1.  Enter a common name to get a scientific name suggestion from NCBI.
2.  Enter a scientific or common name of an organism to view its classification hierarchy (from kingdom to species) and an image (if available).

## 🚀 Technologies Used

*   **Backend:**
    *   Python 3
    *   Flask (for creating API endpoints)
    *   Serverless Functions hosted on Vercel
*   **Frontend:**
    *   HTML5
    *   CSS3
    *   JavaScript (Vanilla JS)
    *   Hosted on GitHub Pages
*   **External APIs:**
    *   [GBIF API (Global Biodiversity Information Facility)](https://www.gbif.org/developer/summary) - For retrieving taxonomic classification data.
    *   [NCBI Entrez API (via Python's `biopython` library)](https://www.ncbi.nlm.nih.gov/books/NBK25497/) - For suggesting scientific names based on common names.
    *   [Wikipedia API (via Python's `wikipedia` library)](https://pypi.org/project/wikipedia/) - For fetching images of organisms.
*   **Key Python Libraries:**
    *   `requests`
    *   `wikipedia`
    *   `biopython` (for NCBI Entrez)
*   **Tools:**
    *   Git & GitHub (for version control and code hosting)

## ✨ Features

*   **Scientific Name Suggestion:**
    *   Enter a common name (e.g., "cat", "lion") to get a scientific name suggestion (e.g., "Felis catus", "Panthera leo") from the NCBI Entrez database.
    *   Option to easily copy the suggested scientific name to the main search input.
*   **Main Taxonomy Search:**
    *   Search organisms by scientific name (and to some extent, common names supported by GBIF).
    *   Display full taxonomic hierarchy (Kingdom, Phylum, Class, Order, Family, Genus, Species).
    *   Show additional information like taxonomic rank, name status, and GBIF match confidence.
    *   Display an image of the organism fetched from Wikipedia (if found), with a smart selection logic.
*   **General:**
    *   Simple, clean, and user-friendly interface with Right-to-Left (RTL) support for Persian.
    *   Responsive design for decent viewing on various devices.
    *   Loading indicators and user-friendly feedback messages for API interactions.
    *   Error handling for API issues and invalid user inputs.

## 🛠️ Challenges & Learnings

*   **API Integration:**
    *   Selecting reliable and suitable APIs for scientific data (GBIF, NCBI, Wikipedia).
    *   Handling different JSON response structures and potential errors from various APIs.
    *   Respecting API rate limits (e.g., for NCBI Entrez).
*   **Backend & Deployment:**
    *   Deploying a Python (Flask) application dificuldades serverlessly on Vercel.
    *   Managing Cross-Origin Resource Sharing (CORS) requests between the frontend (GitHub Pages) and backend (Vercel).
*   **Library-Specific Issues:**
    *   Troubleshooting and resolving `OSError: [Errno 30] Read-only file system` when using `biopython`'s `Bio.Entrez` module in a serverless (read-only filesystem) environment on Vercel. This involved:
        *   Understanding that the library attempts to create a cache directory in a non-writable location during module import.
        *   Implementing a monkey patching solution for `os.makedirs` to temporarily suppress directory creation outside `/tmp` during the critical import phase of `Bio.Entrez.Parser`.
        *   Subsequently redirecting `Bio.Entrez.Parser.DataHandler.local_dtd_dir` to a writable `/tmp` directory.
    *   Ensuring proper `Entrez.email` configuration for NCBI API access.
*   **Frontend Development:**
    *   Implementing logic to select the most relevant image from Wikipedia, which may contain multiple or unrelated images.
    *   Dynamically updating the UI with results and feedback.
*   **Development Process:**
    *   Practicing coding and editing directly on the GitHub platform via its web interface.
    *   Iterative debugging and problem-solving based on browser console logs and Vercel deployment logs.

## 💡 Future Enhancements

*   **UI/UX:**
    *   Implement a more professional visual design (e.g., custom color palette, typography, icons).
    *   Add subtle animations and transitions.
    *   Consider a dark mode option.
    *   Improve accessibility (a11y).
*   **Functionality:**
    *   Allow users to choose from multiple results if a search query (either for NCBI or GBIF) is ambiguous.
    *   Integrate additional APIs for more comprehensive data (e.g., conservation status, distribution maps).
    *   Implement client-side search history using LocalStorage.
    *   Add autocomplete suggestions for search inputs.
*   **Performance:**
    *   Further optimize image loading (e.g., lazy loading).
    *   Minify static assets (CSS, JS).

## 📝 License

This project is licensed under the MIT License.
<!-- If you have a LICENSE.md file, link it: See the [LICENSE](LICENSE.md) file for details. -->

---

Developed by Kaveh ([MyNameisKaveh on GitHub](https://github.com/MyNameisKaveh))
