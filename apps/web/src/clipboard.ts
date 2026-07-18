function legacyCopy(text: string): void {
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.append(field);
  field.select();
  const copied = document.execCommand("copy");
  field.remove();
  if (!copied) throw new Error("clipboard unavailable");
}

export async function writeClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    let timer = 0;
    try {
      await Promise.race([
        navigator.clipboard.writeText(text),
        new Promise<never>((_, reject) => {
          timer = window.setTimeout(() => reject(new Error("clipboard timeout")), 800);
        }),
      ]);
      return;
    } catch {
      // Embedded browsers can expose Clipboard API while leaving its promise pending.
    } finally {
      window.clearTimeout(timer);
    }
  }
  legacyCopy(text);
}
