import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VideoTurboUiTests(unittest.TestCase):
    def test_controls_settings_and_submission(self):
        html = (ROOT / "web/mobile.html").read_text()
        functions = []
        for name in ("updateVideoTurboAvailability", "buildGeneratePayload", "saveSettings", "restoreSettings"):
            match = re.search(r"    function " + name + r"\([^\n]*\) \{.*?\n    \}", html, re.S)
            self.assertIsNotNone(match, name)
            functions.append(match.group())
        code = r'''
const assert = require("node:assert/strict");
const state = {mode: "video", clientId: "local-test", sourceImage: {}, customPromptSource: "", customPrompt: "", customResolution: ""};
const videoTurboInput = {checked: false, disabled: true};
const videoTurboStepsSelect = {value: "8", disabled: true, options: [{value: "8"}, {value: "4"}]};
const videoTurboStepsRow = {hidden: true};
const videoTurboHint = {hidden: false};
const videoModelSelect = {value: "minimax_h3_fl2va_pruned_int8_convrot.safetensors", dataset: {}};
const videoTurboModel = videoModelSelect.value;
const videoInputModeSelect = {value: "text", options: []};
const videoActionInput = {value: "动作"}, videoFpsSelect = {value: "24", options: []}, videoSecondsSelect = {value: "4", options: []};
const scaleSelect = {}, eraSelect = {}, castSelect = {}, shotSelect = {}, orientationSelect = {}, workflowSelect = {};
const zitModelSelect = {dataset: {}}, zibModelSelect = {dataset: {}}, krea2ModelSelect = {dataset: {}};
const imageSeedInput = {value: ""}, imageNegativePrompt = {value: ""};
const settingsKey = "randomPhotoPrompt.mobile.settings";
const storage = new Map();
const localStorage = {setItem: (key, value) => storage.set(key, value), getItem: key => storage.get(key)};
const selectedLoras = () => [], imageKey = () => "", currentCount = () => 1, currentVideoCount = () => 1;
const optionExists = (select, value) => (select.options || []).some(option => option.value === value);
const setSelectValue = (select, value) => {select.value = value;};
const switchMode = () => {}, normalizeStoredShot = () => "", setCount = () => {}, setVideoCount = () => {};
const updateCastAvailability = () => {}, updateCustomPromptButton = () => {}, updateSourcePicker = () => {}, renderCustomSelect = () => {}, closeCustomSelect = () => {};
'''
        code += "\n".join(functions)
        code += r'''
updateVideoTurboAvailability();
assert.equal(videoTurboInput.disabled, false);
assert.equal(videoTurboStepsSelect.disabled, true);
assert.equal(videoTurboStepsRow.hidden, true);
videoTurboInput.checked = true;
updateVideoTurboAvailability();
assert.equal(videoTurboStepsSelect.disabled, false);
assert.equal(videoTurboStepsRow.hidden, false);
for (const steps of [8, 4]) {
  videoTurboStepsSelect.value = String(steps);
  for (const mode of ["text", "image"]) {
    videoInputModeSelect.value = mode;
    const payload = buildGeneratePayload(true, 1);
    assert.equal(payload.turbo, true);
    assert.equal(payload.turbo_steps, steps);
    assert.equal(payload.video_mode, mode);
  }
}
saveSettings();
assert.equal(JSON.parse(storage.get(settingsKey)).videoTurboSteps, 4);
videoTurboStepsSelect.value = "8";
restoreSettings();
assert.equal(videoTurboStepsSelect.value, "4");
videoModelSelect.value = "h3ErosMax_beta5_fp8.safetensors";
updateVideoTurboAvailability();
assert.equal(videoTurboInput.disabled, true);
assert.equal(videoTurboHint.hidden, false);
assert.equal(videoTurboStepsSelect.disabled, true);
assert.equal(videoTurboStepsRow.hidden, true);
assert.equal(buildGeneratePayload(true, 1).turbo, false);
videoModelSelect.value = "MiniMax\\" + videoTurboModel;
updateVideoTurboAvailability();
assert.equal(videoTurboInput.checked, true);
assert.equal(videoTurboStepsSelect.value, "4");
assert.equal(videoTurboStepsSelect.disabled, false);
videoTurboInput.checked = false;
updateVideoTurboAvailability();
assert.equal(videoTurboStepsSelect.disabled, true);
assert.equal(videoTurboStepsRow.hidden, true);
storage.set(settingsKey, JSON.stringify({videoTurbo: true}));
videoTurboStepsSelect.value = "8";
restoreSettings();
assert.equal(videoTurboStepsSelect.value, "8");
'''
        result = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dropdown_defaults_and_change_listeners(self):
        html = (ROOT / "web/mobile.html").read_text()
        select = re.search(r'<select id="videoTurboSteps"[^>]*>(.*?)</select>', html, re.S)
        self.assertIsNotNone(select)
        self.assertRegex(select.group(1), r'<option value="8" selected>8 步</option>')
        self.assertIn('<option value="4">4 步</option>', select.group(1))
        self.assertRegex(html, r'videoTurboInput\.addEventListener\("change", \(\) => \{\s*updateVideoTurboAvailability\(\);\s*saveSettings\(\);')
        self.assertRegex(html, r'\[[^\]\n]*videoTurboStepsSelect[^\]\n]*\]\.forEach\(select => \{\s*select\.addEventListener\("change",')


if __name__ == "__main__":
    unittest.main()
