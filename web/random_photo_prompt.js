import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const RANDOM_PHOTO_NODE = "RandomPhotoPrompt";
const IMAGE_INTERROGATOR_NODE = "RandomPhotoImageInterrogator";
const CACHE_WIDGET_NAMES = new Set(["cached_prompt", "cached_negative_prompt", "cached_signature", "cached_aspect", "cached_prompt_source"]);
const USE_PREGENERATED_WIDGET_NAME = "use_pregenerated_prompt";
const AUTO_RESOLUTION_WIDGET_NAME = "auto_resolution";
const PROMPT_RULE_WIDGET_NAME = "prompt_rule";
const DISPLAY_WIDGET_LABELS = {
  shot: "镜头",
  scale: "档位",
  use_pregenerated_prompt: "固定提示词",
  prompt_rule: "提示词规则",
};
const PREGENERATE_WIDGET_NAME = "预生成提示词";
const SELECT_IMAGE_WIDGET_NAME = "选择反推图片";
const INTERROGATE_WIDGET_NAME = "反推提示词";
const IMAGE_PREVIEW_HEIGHT = 150;
const IMAGE_PREVIEW_MARGIN = 12;
const IMAGE_PREVIEW_RADIUS = 6;
const NODE_STATUS_HEIGHT = 22;
const RESOLUTION_MULTIPLE = 8;
const IMAGE_FILENAME_PATTERN = /[\w\u4e00-\u9fff .()[\]{}@+\-=#%]+?\.(?:png|jpe?g|webp|gif|bmp)/gi;

function findWidget(node, names, predicate = null) {
  return node?.widgets?.find((widget) => {
    if (names?.includes(widget.name)) return true;
    if (names?.includes(widget.label)) return true;
    return predicate?.(widget) ?? false;
  });
}

function widgetValue(node, name, fallback = "") {
  return findWidget(node, [name])?.value ?? fallback;
}

function setWidgetValue(node, value) {
  const widget = findWidget(
    node,
    ["text", "文本"],
    (item) => item.type === "customtext" || item.type === "STRING"
  );
  if (!widget) return false;
  widget.value = value;
  if (widget.inputEl) {
    widget.inputEl.value = value;
    widget.inputEl.dispatchEvent(new Event("input", { bubbles: true }));
    widget.inputEl.dispatchEvent(new Event("change", { bubbles: true }));
  }
  widget.callback?.(value);
  return true;
}

function textWidgetValue(node) {
  const widget = findWidget(
    node,
    ["text", "文本"],
    (item) => item.type === "customtext" || item.type === "STRING"
  );
  return widget?.value ?? "";
}

function setNamedWidgetValue(node, name, value) {
  const widget = findWidget(node, [name]);
  if (!widget) return false;
  widget.value = value;
  widget.callback?.(value);
  return true;
}

function setAnyWidgetValue(node, names, value) {
  const widget = findWidget(node, names);
  if (!widget) return false;
  widget.value = value;
  if (widget.inputEl) {
    widget.inputEl.value = value;
    widget.inputEl.dispatchEvent(new Event("input", { bubbles: true }));
    widget.inputEl.dispatchEvent(new Event("change", { bubbles: true }));
  }
  widget.callback?.(value);
  return true;
}

function extractAssetDeleteFilenames(dialog) {
  const text = dialog?.innerText || "";
  return Array.from(new Set((text.match(IMAGE_FILENAME_PATTERN) || []).map((item) => item.trim())));
}

async function deleteLocalProxyAsset(filename) {
  if (!filename) return;
  try {
    await api.fetchApi("/random_photo_prompt/proxy/delete_local_asset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    });
  } catch (error) {
    console.warn("[random_photo_prompt] Failed to delete local proxy asset", filename, error);
  }
}

function installLocalAssetDeleteBridge() {
  document.addEventListener(
    "click",
    (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest("button");
      if (!button || !/删除/.test(button.innerText || "")) return;
      const dialog = button.closest('[role="dialog"]');
      if (!dialog || !/删除此资产/.test(dialog.innerText || "")) return;
      const filenames = extractAssetDeleteFilenames(dialog);
      if (!filenames.length) return;
      setTimeout(() => {
        for (const filename of filenames) deleteLocalProxyAsset(filename);
      }, 0);
    },
    true
  );
}

function applyDisplayWidgetLabels(node) {
  for (const widget of node.widgets ?? []) {
      const label = DISPLAY_WIDGET_LABELS[widget.name];
      if (widget.name === AUTO_RESOLUTION_WIDGET_NAME) {
        widget.label = "自动分辨率";
        widget.options ??= {};
        widget.options.label = "自动分辨率";
        continue;
      }
      if (!label) continue;
    widget.label = label;
    widget.options ??= {};
    widget.options.label = label;
  }
}

function normalizeAspect(value) {
  const text = String(value || "").trim().toLowerCase();
  if (["landscape", "horizontal", "横屏", "横向", "wide"].includes(text)) return "landscape";
  return "portrait";
}

function promptSignature(node, aspect = currentWorkflowAspect().aspect) {
  return `${widgetValue(node, "scale", "")}|${widgetValue(node, "shot", "")}|${normalizeAspect(aspect)}`;
}

function usePregeneratedPrompt(node) {
  const value = widgetValue(node, USE_PREGENERATED_WIDGET_NAME, true);
  if (value === false || value === 0) return false;
  if (typeof value === "string") {
    return !["false", "0", "off", "no"].includes(value.trim().toLowerCase());
  }
  return true;
}

function useAutoResolution(node) {
  const value = widgetValue(node, AUTO_RESOLUTION_WIDGET_NAME, true);
  if (value === false || value === 0) return false;
  if (typeof value === "string") {
    return !["false", "0", "off", "no"].includes(value.trim().toLowerCase());
  }
  return true;
}

function selectedPromptRule(node) {
  return String(widgetValue(node, PROMPT_RULE_WIDGET_NAME, "规则1") || "规则1").trim();
}

function setNodeImagePreview(node, file) {
  if (node.__randomPhotoPreviewUrl) {
    URL.revokeObjectURL(node.__randomPhotoPreviewUrl);
  }
  const url = URL.createObjectURL(file);
  const image = new Image();
  node.__randomPhotoPreviewUrl = url;
  node.__randomPhotoPreviewImage = image;
  node.__randomPhotoPreviewName = file.name || "image";
  image.onload = () => {
    node.setSize?.(node.computeSize?.() ?? node.size);
    app.graph?.setDirtyCanvas?.(true, true);
  };
  image.src = url;
  node.setSize?.(node.computeSize?.() ?? node.size);
  app.graph?.setDirtyCanvas?.(true, true);
}

function openImagePicker(node) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.style.display = "none";
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    input.remove();
    if (!file) return;
    node.__randomPhotoSelectedFile = file;
    setNodeImagePreview(node, file);
    setNodeStatus(node, `已选择图片：${file.name || "image"}`);
  });
  document.body.appendChild(input);
  input.click();
}

async function requestImageInterrogation(file) {
  const form = new FormData();
  form.append("image", file, file.name || "image.png");
  const response = await api.fetchApi("/random_photo_prompt/interrogate", {
    method: "POST",
    body: form,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_error) {
    data = null;
  }
  if (!response.ok) {
    throw new Error(data?.error || text || `HTTP ${response.status}`);
  }
  return data ?? {};
}

async function interrogateSelectedImage(node) {
  const file = node.__randomPhotoSelectedFile;
  if (!file) {
    openImagePicker(node);
    setNodeStatus(node, "请先选择一张反推图片");
    return false;
  }
  setNodeStatus(node, "正在反推提示词...");
  const result = await requestImageInterrogation(file);
  if (!result.prompt) {
    setNodeStatus(node, "反推失败：没有收到提示词");
    return false;
  }
  const frame = currentWorkflowAspect();
  const signature = result.signature || `interrogate|${Date.now()}`;
  const applied = await applyPromptToNodeAndClips(node, result.prompt, signature, frame.aspect);
  setNodeStatus(node, applied ? "反推完成，已写入连接的文本节点" : "反推完成，但未连接 CLIP 文本节点");
  return true;
}

function setNodeStatus(node, text) {
  node.__randomPhotoStatus = text || "";
  node.setSize?.(node.computeSize?.() ?? node.size);
  app.graph?.setDirtyCanvas?.(true, true);
}

function drawRoundedRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function drawNodeImagePreview(node, ctx) {
  const status = node.__randomPhotoStatus;
  if (status) {
    const margin = IMAGE_PREVIEW_MARGIN;
    const x = margin;
    const y = Math.max(0, node.size[1] - NODE_STATUS_HEIGHT - margin);
    const width = Math.max(80, node.size[0] - margin * 2);
    ctx.save();
    ctx.fillStyle = "#2a2a2a";
    ctx.fillRect(x, y, width, NODE_STATUS_HEIGHT);
    ctx.fillStyle = "#d6d6d6";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(status, x + 8, y + NODE_STATUS_HEIGHT / 2);
    ctx.restore();
  }

  const image = node.__randomPhotoPreviewImage;
  if (!image) return;

  const margin = IMAGE_PREVIEW_MARGIN;
  const width = Math.max(80, node.size[0] - margin * 2);
  const height = IMAGE_PREVIEW_HEIGHT;
  const x = margin;
  const statusOffset = status ? NODE_STATUS_HEIGHT + margin : 0;
  const y = Math.max(0, node.size[1] - height - margin - statusOffset);

  ctx.save();
  drawRoundedRect(ctx, x, y, width, height, IMAGE_PREVIEW_RADIUS);
  ctx.fillStyle = "#1f1f1f";
  ctx.fill();
  ctx.strokeStyle = "#555";
  ctx.lineWidth = 1;
  ctx.stroke();

  if (image.complete && image.naturalWidth && image.naturalHeight) {
    const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight);
    const drawWidth = image.naturalWidth * scale;
    const drawHeight = image.naturalHeight * scale;
    const drawX = x + (width - drawWidth) / 2;
    const drawY = y + (height - drawHeight) / 2;
    ctx.clip();
    ctx.drawImage(image, drawX, drawY, drawWidth, drawHeight);
  } else {
    ctx.fillStyle = "#9a9a9a";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("loading image", x + width / 2, y + height / 2);
  }
  ctx.restore();
}

function isClipTextEncode(node) {
  const type = String(node?.type || node?.comfyClass || "");
  const title = String(node?.title || "");
  const text = `${type} ${title}`;
  return type.includes("CLIPTextEncode") || title.includes("CLIP文本编码") || title.includes("CLIPTextEncode");
}

function connectedClipNodes(node, outputIndex = 0) {
  const output = node?.outputs?.[outputIndex];
  const links = Array.isArray(output?.links) ? output.links : [];
  if (!links.length) return [];
  const nodes = [];
  for (const linkId of links) {
    const link = app.graph?.links?.[linkId];
    if (!link) continue;
    const target = app.graph.getNodeById?.(link.target_id);
    if (isClipTextEncode(target)) nodes.push(target);
  }
  return nodes;
}

function allConnectedClipNodes(node) {
  const clips = [];
  const seen = new Set();
  for (let index = 0; index < (node?.outputs?.length ?? 0); index += 1) {
    for (const clip of connectedClipNodes(node, index)) {
      if (seen.has(clip.id)) continue;
      seen.add(clip.id);
      clips.push(clip);
    }
  }
  return clips;
}

async function requestPrompt(node) {
  const scale = widgetValue(node, "scale", "二档");
  const shot = widgetValue(node, "shot", "默认");
  const frame = currentWorkflowAspect();
  const response = await api.fetchApi("/random_photo_prompt/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scale,
      shot,
      aspect: frame.aspect,
      width: frame.width,
      height: frame.height,
      seed: `${Date.now()}_${node.id}_${Math.random()}`,
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return await response.json();
}

async function requestKeywordExpansion(node) {
  const frame = currentWorkflowAspect();
  const scale = widgetValue(node, "scale", "二档");
  const shot = widgetValue(node, "shot", "默认");
  const response = await api.fetchApi("/random_photo_prompt/keyword_expand", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scale,
      shot,
      aspect: frame.aspect,
      seed: `${Date.now()}_${node.id}_${Math.random()}`,
    }),
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_error) {
    data = null;
  }
  if (!response.ok) {
    throw new Error(data?.error || text || `HTTP ${response.status}`);
  }
  return data ?? {};
}

async function requestResolutionForPrompt(node, prompt) {
  const response = await api.fetchApi("/random_photo_prompt/resolve_resolution", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      shot: widgetValue(node, "shot", "全身"),
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return await response.json();
}

function numericWidgetValue(node, names) {
  const widget = findWidget(node, names);
  const value = Number(widget?.value);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function roundToMultiple(value, multiple = RESOLUTION_MULTIPLE) {
  return Math.max(multiple, Math.round(Number(value) / multiple) * multiple);
}

function sizeCandidateFromNode(node) {
  const width = numericWidgetValue(node, ["width", "Width", "宽度", "image_width", "图像宽度"]);
  const height = numericWidgetValue(node, ["height", "Height", "高度", "image_height", "图像高度"]);
  if (!width || !height) return null;
  return { width, height };
}

function isImageSizeNode(node) {
  const type = String(node?.type || node?.comfyClass || "");
  const title = String(node?.title || "");
  const text = `${type} ${title}`;
  return (
    type.includes("EmptyLatent") ||
    type.includes("LatentImage") ||
    type.includes("ImageSize") ||
    text.includes("Aspect Ratio") ||
    text.includes("宽高比") ||
    title.includes("空Latent") ||
    title.includes("Latent图像") ||
    title.includes("图像尺寸")
  );
}

function isNodeEnabled(node) {
  const mode = Number(node?.mode ?? 0);
  return mode !== 2 && mode !== 4;
}

function linkedWidgetValue(node, widgetNames, fallback = 1) {
  for (const input of node.inputs ?? []) {
    if (!widgetNames.includes(input.name) || input.link == null) continue;
    const value = linkedNumericValue(input.link);
    if (value) return value;
  }
  const direct = numericWidgetValue(node, widgetNames);
  if (direct) return direct;
  return fallback;
}

function linkedNumericValue(linkId, visited = new Set()) {
  if (linkId == null || visited.has(linkId)) return null;
  visited.add(linkId);
  const link = app.graph?.links?.[linkId];
  const source = app.graph?.getNodeById?.(link?.origin_id);
  if (!source) return null;
  const direct = numericWidgetValue(source, ["value", "Value"]);
  if (direct) return direct;
  const type = String(source?.type || source?.comfyClass || "");
  if (type === "Reroute") {
    for (const input of source.inputs ?? []) {
      const value = linkedNumericValue(input.link, visited);
      if (value) return value;
    }
  }
  return null;
}

function workflowOutputScale() {
  let scale = 1;
  for (const node of app.graph?._nodes ?? []) {
    if (!isNodeEnabled(node)) continue;
    const type = String(node?.type || node?.comfyClass || "");
    if (type === "LatentUpscaleBy") {
      scale *= linkedWidgetValue(node, ["scale_by", "Scale By"], 1);
      continue;
    }
    if (type === "UltimateSDUpscale") {
      scale *= linkedWidgetValue(node, ["upscale_by", "Upscale By", "upscale by"], 1);
    }
  }
  return Number.isFinite(scale) && scale > 0 ? scale : 1;
}

function applyResolutionToWorkflow(width, height) {
  const nextWidth = Number(width);
  const nextHeight = Number(height);
  if (!Number.isFinite(nextWidth) || !Number.isFinite(nextHeight) || nextWidth <= 0 || nextHeight <= 0) {
    return 0;
  }
  const scale = workflowOutputScale();
  const baseWidth = roundToMultiple(nextWidth / scale);
  const baseHeight = roundToMultiple(nextHeight / scale);
  let patched = 0;
  for (const node of app.graph?._nodes ?? []) {
    if (!isNodeEnabled(node)) continue;
    if (!isImageSizeNode(node)) continue;
    const changedWidth = setAnyWidgetValue(node, ["width", "Width", "宽度", "瀹藉害", "image_width", "图像宽度", "鍥惧儚瀹藉害"], baseWidth);
    const changedHeight = setAnyWidgetValue(node, ["height", "Height", "高度", "楂樺害", "image_height", "图像高度", "鍥惧儚楂樺害"], baseHeight);
    if (changedWidth || changedHeight) patched += 1;
  }
  if (patched) app.graph?.setDirtyCanvas?.(true, true);
  return patched;
}

function currentWorkflowAspect() {
  const candidates = [];
  for (const node of app.graph?._nodes ?? []) {
    if (!isNodeEnabled(node)) continue;
    const size = sizeCandidateFromNode(node);
    if (size) candidates.push(size);
  }
  const selected = candidates[0] ?? null;
  if (!selected) return { aspect: "portrait", width: null, height: null };
  return {
    aspect: selected.width > selected.height ? "landscape" : "portrait",
    width: selected.width,
    height: selected.height,
  };
}

async function applyPromptToNodeAndClips(node, prompt, signature = promptSignature(node), aspect = currentWorkflowAspect().aspect, negativePrompt = "", source = "") {
  if (!prompt) return false;
  setNamedWidgetValue(node, "cached_prompt", prompt);
  setNamedWidgetValue(node, "cached_negative_prompt", negativePrompt || "");
  setNamedWidgetValue(node, "cached_signature", signature || promptSignature(node));
  setNamedWidgetValue(node, "cached_aspect", normalizeAspect(aspect));
  setNamedWidgetValue(node, "cached_prompt_source", source || "");
  const positiveClips = connectedClipNodes(node, 0);
  const negativeClips = connectedClipNodes(node, 1);
  for (const clip of positiveClips) {
    setWidgetValue(clip, prompt);
  }
  for (const clip of negativeClips) {
    setWidgetValue(clip, negativePrompt || "");
  }
  app.graph?.setDirtyCanvas?.(true, true);
  return Boolean(positiveClips.length || negativeClips.length);
}

async function prepareNodePrompt(node, { force = false } = {}) {
  const clips = allConnectedClipNodes(node);
  if (!clips.length) {
    setNodeStatus(node, "未连接 CLIP 文本节点，跳过预生成和自动分辨率");
    return false;
  }
  const cachedPrompt = widgetValue(node, "cached_prompt", "");
  const cachedNegativePrompt = widgetValue(node, "cached_negative_prompt", "");
  const cachedSignature = widgetValue(node, "cached_signature", "");
  const cachedPromptSource = widgetValue(node, "cached_prompt_source", "");
  const frame = currentWorkflowAspect();
  if (!force && usePregeneratedPrompt(node) && cachedPrompt) {
    if (useAutoResolution(node) && cachedPromptSource !== "keyword_expansion") {
      try {
        const resolution = await requestResolutionForPrompt(node, cachedPrompt);
        if (resolution?.width && resolution?.height) {
          applyResolutionToWorkflow(resolution.width, resolution.height);
        }
      } catch (error) {
        console.warn("[random_photo_prompt] Failed to resolve fixed prompt resolution", error);
      }
    }
    for (const clip of connectedClipNodes(node, 0)) {
      setWidgetValue(clip, cachedPrompt);
    }
    for (const clip of connectedClipNodes(node, 1)) {
      setWidgetValue(clip, cachedNegativePrompt);
    }
    setNodeStatus(node, "已使用固定提示词");
    return true;
  }
  if (selectedPromptRule(node) === "规则2") {
    return await prepareKeywordExpansionPrompt(node);
  }
  setNodeStatus(node, "正在预生成提示词...");
  const result = await requestPrompt(node);
  if (!result?.prompt) {
    setNodeStatus(node, "预生成失败：没有收到提示词");
    return false;
  }
  if (useAutoResolution(node)) {
    applyResolutionToWorkflow(result.width, result.height);
  }
  const applied = await applyPromptToNodeAndClips(
    node,
    result.prompt,
    result.signature || promptSignature(node, result.aspect),
    result.aspect || frame.aspect,
    result.negative_prompt || "",
    result.source || "random_photo_prompt"
  );
  setNodeStatus(node, applied ? "预生成完成，已写入连接的文本节点" : "预生成完成，但未连接 CLIP 文本节点");
  return true;
}

async function prepareKeywordExpansionPrompt(node) {
  const clips = allConnectedClipNodes(node);
  if (!clips.length) {
    setNodeStatus(node, "未连接 CLIP 文本节点，无法写入关键词扩写");
    return false;
  }
  setNodeStatus(node, "正在生成小助手式提示词...");
  const result = await requestKeywordExpansion(node);
  if (!result?.prompt) {
    setNodeStatus(node, "关键词扩写失败：没有收到提示词");
    return false;
  }
  const frame = currentWorkflowAspect();
  const applied = await applyPromptToNodeAndClips(
    node,
    result.prompt,
    result.signature || `assistant_style|${Date.now()}`,
    result.aspect || frame.aspect,
    result.negative_prompt || "",
    "keyword_expansion"
  );
  setNodeStatus(node, applied ? "小助手式提示词完成，已写入连接的文本节点" : "小助手式提示词完成，但未连接 CLIP 文本节点");
  return true;
}

async function prepareRandomPhotoPrompts() {
  const nodes = app.graph?._nodes?.filter((node) => node.type === RANDOM_PHOTO_NODE) ?? [];
  for (const node of nodes) {
    try {
      await prepareNodePrompt(node, { force: !usePregeneratedPrompt(node) });
    } catch (error) {
      console.error("[random_photo_prompt] Failed to prepare prompt before queue", error);
      setNodeStatus(node, `预生成失败：${error.message || error}`);
    }
  }
  app.graph?.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "random_photo_prompt.queue_sync_clip",
  init() {
    installLocalAssetDeleteBridge();
    const graphToPrompt = app.graphToPrompt;
    app.graphToPrompt = async function () {
      try {
        await prepareRandomPhotoPrompts();
      } catch (error) {
        console.error("[random_photo_prompt] Prompt preparation failed; continuing queue", error);
      }
      return await graphToPrompt.apply(this, arguments);
    };
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (![RANDOM_PHOTO_NODE, IMAGE_INTERROGATOR_NODE].includes(nodeData.name)) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const isInterrogator = nodeData.name === IMAGE_INTERROGATOR_NODE || this.type === IMAGE_INTERROGATOR_NODE;
      if (!isInterrogator) applyDisplayWidgetLabels(this);
      for (const widget of this.widgets ?? []) {
        if (!CACHE_WIDGET_NAMES.has(widget.name)) continue;
        widget.computeSize = () => [0, -4];
        widget.hidden = true;
      }
      const fixedWidget = findWidget(this, [USE_PREGENERATED_WIDGET_NAME]);
      if (!isInterrogator && fixedWidget && !fixedWidget.__randomPhotoLockHooked) {
        const originalCallback = fixedWidget.callback;
        fixedWidget.callback = (value) => {
          originalCallback?.call(fixedWidget, value);
          if (!usePregeneratedPrompt(this)) return;
          const positiveClip = connectedClipNodes(this, 0)[0];
          const negativeClip = connectedClipNodes(this, 1)[0];
          const currentPrompt = widgetValue(this, "cached_prompt", "") || textWidgetValue(positiveClip);
          if (!currentPrompt) {
            setNodeStatus(this, "请先预生成提示词，再固定");
            return;
          }
          setNamedWidgetValue(this, "cached_prompt", currentPrompt);
          setNamedWidgetValue(this, "cached_negative_prompt", widgetValue(this, "cached_negative_prompt", "") || textWidgetValue(negativeClip));
          const frame = currentWorkflowAspect();
          setNamedWidgetValue(this, "cached_signature", promptSignature(this, frame.aspect));
          setNamedWidgetValue(this, "cached_aspect", normalizeAspect(frame.aspect));
          setNamedWidgetValue(this, "cached_prompt_source", widgetValue(this, "cached_prompt_source", "") || "manual_fixed");
          setNodeStatus(this, "已固定当前提示词");
          app.graph?.setDirtyCanvas?.(true, true);
        };
        fixedWidget.__randomPhotoLockHooked = true;
      }
      if (!isInterrogator && !findWidget(this, [PREGENERATE_WIDGET_NAME])) {
        this.addWidget?.("button", PREGENERATE_WIDGET_NAME, null, async () => {
          try {
            await prepareNodePrompt(this, { force: true });
            app.graph?.setDirtyCanvas?.(true, true);
          } catch (error) {
            console.error("[random_photo_prompt] Failed to pregenerate prompt", error);
            setNodeStatus(this, `预生成失败：${error.message || error}`);
            alert(`预生成提示词失败：${error.message || error}`);
          }
        });
      }
      if (isInterrogator && !findWidget(this, [SELECT_IMAGE_WIDGET_NAME])) {
        this.addWidget?.("button", SELECT_IMAGE_WIDGET_NAME, null, () => openImagePicker(this));
      }
      if (isInterrogator && !findWidget(this, [INTERROGATE_WIDGET_NAME])) {
        this.addWidget?.("button", INTERROGATE_WIDGET_NAME, null, async () => {
          try {
            await interrogateSelectedImage(this);
            app.graph?.setDirtyCanvas?.(true, true);
          } catch (error) {
            console.error("[random_photo_prompt] Failed to interrogate image", error);
            setNodeStatus(this, `反推失败：${error.message || error}`);
            alert(`反推提示词失败：${error.message || error}`);
          }
        });
      }
      this.setSize?.(this.computeSize?.() ?? this.size);
    };

    const computeSize = nodeType.prototype.computeSize;
    nodeType.prototype.computeSize = function () {
      const size = computeSize?.apply(this, arguments) ?? this.size ?? [280, 120];
      const nextSize = [size[0], size[1]];
      if (this.__randomPhotoPreviewImage) {
        nextSize[1] = size[1] + IMAGE_PREVIEW_HEIGHT + IMAGE_PREVIEW_MARGIN;
      }
      if (this.__randomPhotoStatus) {
        nextSize[1] += NODE_STATUS_HEIGHT + IMAGE_PREVIEW_MARGIN;
      }
      return nextSize;
    };

    const onDrawForeground = nodeType.prototype.onDrawForeground;
    nodeType.prototype.onDrawForeground = function (ctx) {
      onDrawForeground?.apply(this, arguments);
      drawNodeImagePreview(this, ctx);
    };
  },
});

