import './styles.css';

const releaseLink = document.querySelector<HTMLAnchorElement>('#latest-release');

async function refreshRelease(): Promise<void> {
  if (releaseLink === null) {
    return;
  }

  const fallbackVersion = releaseLink.dataset.fallbackVersion ?? releaseLink.textContent ?? '';
  try {
    const response = await fetch('https://api.github.com/repos/VectorTrace-Labs/ActionLineage/releases/latest', {
      headers: {
        Accept: 'application/vnd.github+json'
      }
    });
    if (!response.ok) {
      releaseLink.textContent = fallbackVersion;
      return;
    }
    const payload = (await response.json()) as { tag_name?: unknown; html_url?: unknown };
    const tagName = typeof payload.tag_name === 'string' ? payload.tag_name : fallbackVersion;
    const releaseUrl =
      typeof payload.html_url === 'string'
        ? payload.html_url
        : 'https://github.com/VectorTrace-Labs/ActionLineage/releases';
    releaseLink.textContent = tagName;
    releaseLink.href = releaseUrl;
  } catch {
    releaseLink.textContent = fallbackVersion;
  }
}

void refreshRelease();
