/*
在你自己的正常 Chrome 会话里打开 fangdi 查询页并能看到验证码后，
把这段脚本粘到 DevTools Console 执行。

它会：
1. 自动找到验证码图片
2. 连续下载若干张验证码到默认下载目录
3. 每次下载后点击验证码图片刷新下一张

建议：
- 先把 Chrome 的默认下载目录设成一个单独文件夹
- 首次运行时允许“此网站下载多个文件”
*/

(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const attempts = 30;

  const img =
    document.querySelector('img[src*="captcha"], img[src*="verify"]') ||
    (() => {
      const label = [...document.querySelectorAll("*")].find((el) =>
        /验证码/.test((el.textContent || "").trim())
      );
      if (!label) return null;
      const imgs = [...document.querySelectorAll("img")];
      return imgs.find((candidate) =>
        candidate.compareDocumentPosition(label) &
        Node.DOCUMENT_POSITION_PRECEDING
          ? false
          : true
      );
    })();

  if (!img) {
    console.error("没有找到验证码图片，请确认当前页面已经显示查询表单。");
    return;
  }

  const getBytes = async (url) => {
    const res = await fetch(url, { credentials: "include", cache: "no-store" });
    if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
    return await res.blob();
  };

  const downloadBlob = (blob, filename) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 1000);
  };

  for (let i = 1; i <= attempts; i++) {
    const src = img.src;
    try {
      const blob = await getBytes(src);
      const filename = `fangdi-captcha-${String(i).padStart(3, "0")}.png`;
      downloadBlob(blob, filename);
      console.log(`downloaded ${filename}`);
    } catch (err) {
      console.error(`attempt ${i} failed`, err);
    }

    img.click();
    await sleep(1200);
  }

  console.log("done");
})();
