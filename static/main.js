function copyToClipboard(text) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      alert('Lien copié !');
    }).catch(() => {
      prompt('Copie le lien :', text);
    });
  } else {
    prompt('Copie le lien :', text);
  }
}
