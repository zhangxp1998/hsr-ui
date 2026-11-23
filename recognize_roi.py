"""Sprite-first guide layout, ROI detection, and title-only batched OCR.

No device access. Templates and geometry have separate, explicit provenance.
The page gate never calls OCR. Text is recognized only for visible sub-tab titles.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time

HERE = Path(__file__).resolve().parent
from recognize_guide import catalog, feature, cv2, np, Image

PARAMS = {
    'EngineConfig.onnxruntime.use_cuda': os.environ.get('HSR_UI_OCR_CUDA') == '1',
    'EngineConfig.onnxruntime.intra_op_num_threads': 4,
    'EngineConfig.onnxruntime.inter_op_num_threads': 1,
    'EngineConfig.onnxruntime.cuda_ep_cfg.cudnn_conv_algo_search': 'HEURISTIC',
    'Global.use_cls': False,
    'Global.max_side_len': 2200,
    'Global.text_score': .5,
    # A minimum-side policy would UPSCALE this small ROI back to a large tensor.
    'Det.limit_type': 'max',
    'Det.limit_side_len': 960,
}
RECOGNITION_PARAMS = dict(PARAMS, **{'EngineConfig.onnxruntime.use_cuda': False})


class SpriteMatcher:
    def __init__(self):
        # Weak optional logo is not needed for the distinctive five-tab page gate.
        self.records = [x for x in catalog() if x['id'] != 'guide_logo']
        self.bases = {}
        self.templates = {}
        for x in self.records:
            rgba = np.array(Image.open(x['template']).convert('RGBA'))
            rgb = (rgba[:, :, :3] * (rgba[:, :, 3:4] / 255)).astype(np.uint8)
            self.bases[x['id']] = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def pyramid(self, rec, image_height):
        key = (rec['id'], image_height)
        if key not in self.templates:
            base = self.bases[rec['id']]
            levels = []
            for nh in range(rec['heights'][0], rec['heights'][1] + 1, 2):
                s = nh * image_height / 1440 / base.shape[0] * .5
                levels.append((nh, feature(cv2.resize(base, None, fx=s, fy=s,
                                                      interpolation=cv2.INTER_AREA))))
            self.templates[key] = levels
        return self.templates[key]

    def __call__(self, im):
        h, w = im.shape[:2]
        targets, deviations, out = {}, {}, []
        for rec in self.records:
            box = tuple(round(v * size) for v, size in zip(rec['roi'], [w, h, w, h]))
            l, t, r, b = box
            if box not in targets:
                targets[box] = feature(cv2.resize(im[t:b, l:r], None, fx=.5, fy=.5,
                                                  interpolation=cv2.INTER_AREA))
            target = targets[box]
            best = None
            for nh, temp in self.pyramid(rec, h):
                th, tw = temp.shape
                if th > target.shape[0] or tw > target.shape[1]:
                    continue
                response = cv2.matchTemplate(target, temp, cv2.TM_CCOEFF_NORMED)
                k = (box, th, tw)
                if k not in deviations:
                    mean = cv2.boxFilter(target, -1, (tw, th), anchor=(0, 0))
                    sq = cv2.boxFilter(target * target, -1, (tw, th), anchor=(0, 0))
                    deviations[k] = np.sqrt(np.maximum(0, sq - mean * mean))[
                        :response.shape[0], :response.shape[1]]
                score_map = np.abs(response) if rec['allow_inversion'] else response.copy()
                score_map[deviations[k] < .015] = -1
                _, score, _, (x, y) = cv2.minMaxLoc(score_map)
                if best is None or score > best['score']:
                    signed = float(response[y, x])
                    best = dict(id=rec['id'], label=rec['label'], asset_name=rec['asset_name'],
                                role=rec['role'], score=float(score), signed_ncc=signed,
                                bounds=[l+2*x, t+2*y, l+2*(x+tw), t+2*(y+th)],
                                nominal_height=nh, accepted=bool(score >= .80),
                                selected_candidate=signed < 0 if rec['role'] == 'main_tab' else None,
                                template_source='original_game_sprite',
                                template_sha256=rec['template_sha256'])
            if best is not None:
                out.append(best)
        return out


def center(match):
    l, t, r, b = match['bounds']
    return np.array([(l+r)/2, (t+b)/2])


def locate_layout(im, matches, profile):
    main = [m for m in matches if m['accepted'] and m['role'] == 'main_tab']
    close = next((m for m in matches if m['accepted'] and m['id'] == 'close'), None)
    result = dict(accepted=False, reason='insufficient_original_anchors',
                  main_tabs=sorted(main, key=lambda m: m['bounds'][0]),
                  selected_main_tab=None, selected_main_label=None,
                  ocr_title_used=False, subtab_roi=None)
    if len(main) < 4 or close is None:
        return result
    ref = np.array([profile['main_centers'][m['id']] for m in main])
    obs = np.array([center(m) for m in main])
    ratios = [(obs[j, 0]-obs[i, 0])/(ref[j, 0]-ref[i, 0])
              for i in range(len(main)) for j in range(i+1, len(main))]
    scale = float(np.median(ratios))
    offset = np.median(obs - ref * scale, axis=0)
    errors = np.linalg.norm(obs - (ref * scale + offset), axis=1)
    close_error = float(np.linalg.norm(center(close) -
                                      (np.array(profile['close_center'])*scale + offset)))
    nominal_scale = im.shape[0] / profile['reference_dimensions'][1]
    row_ok = (.8*nominal_scale < scale < 1.2*nominal_scale
              and float(errors.max()) < 6*scale and close_error < 18*scale)
    selected = [m for m in main if m['selected_candidate']]
    result.update(scale=scale, offset=offset.tolist(),
                  max_anchor_residual_px=float(errors.max()), close_residual_px=close_error,
                  geometry_kind=profile['geometry_kind'])
    if not row_ok:
        result['reason'] = 'inconsistent_anchor_geometry'
        return result
    if len(selected) != 1:
        result['reason'] = 'selected_main_unknown'
        return result
    result.update(accepted=True, reason='original_sprite_identity_order_geometry_and_polarity',
                  selected_main_tab=selected[0]['id'], selected_main_label=selected[0]['label'])
    if selected[0]['id'] == 'training':
        result['ocr_skip_reason'] = 'no_subtab_list_in_this_verified_layout'
        return result
    r = np.array(profile['subtabs_roi_reference'], dtype=float)
    r = r * scale + np.tile(offset, 2)
    h, w = im.shape[:2]
    r = np.rint(r).astype(int)
    if r[0] < 0 or r[1] < 0 or r[2] > w or r[3] > h:
        result.update(accepted=False, reason='layout_roi_out_of_view')
        return result
    result['subtab_roi'] = r.tolist()
    return result


def make_tabs(im, regions, layout):
    s = layout['scale']
    dx, dy = layout['offset']
    regions = sorted(regions, key=lambda x: x['bounds'][1])
    regions = [x for x in regions if x['score'] >= .5 and len(x['text']) >= 3
               and re.search(r'[\u4e00-\u9fff]', x['text'])]
    ys = [(x['bounds'][1]+x['bounds'][3])/2 for x in regions]
    diffs = [v for v in np.diff(ys) if 120*s < v < 230*s]
    pitch = float(np.median(diffs)) if diffs else 172*s
    tabs = []
    for x in regions:
        x0, y0, x1, y1 = x['bounds']
        top = (y0+y1)/2 - (.42 if layout['selected_main_tab'] == 'cosmic' else .25)*pitch
        box = [max(dx+170*s, x0-.35*pitch), max(dy+384*s, top),
               min(dx+737*s, x0+2.8*pitch), min(dy+1184*s, top+.84*pitch)]
        xa, xb = round(x0+.09*pitch), round(x0+1.86*pitch)
        ya, yb = round(y1+.035*pitch), round(y1+.12*pitch)
        strip = im[max(0, ya):min(im.shape[0], yb), max(0, xa):min(im.shape[1], xb)]
        gray = float(np.median(cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY))) if strip.size else None
        tabs.append(dict(raw_text=x['text'], ocr_score=x['score'], text_bounds=x['bounds'],
                         text_polygon=x['polygon'], row_bounds_candidate=box,
                         selected_candidate=gray is not None and gray < 95,
                         selection_strip_gray_median=gray,
                         geometry_kind='inferred card; not engine/touch bounds'))
    selected = [x for x in tabs if x['selected_candidate']]
    for tab in tabs:
        tab['selected'] = (tab is selected[0]) if len(selected) == 1 else None
    return tabs, selected[0]['raw_text'] if len(selected) == 1 else None


class GuideRecognizer:
    def __init__(self, reuse_ocr=False):
        self.matcher = SpriteMatcher()
        self.profile = json.loads((HERE/'layout-profile.json').read_text())
        self.engine = None  # Main-tab-only and negative frames never load OCR.
        self.recognition_engine = None
        self.reuse_ocr = reuse_ocr
        self.cache = None  # One exact ROI, scoped to this immutable profile/model instance.

    def get_engine(self):
        if self.engine is None:
            from rapidocr import RapidOCR
            if PARAMS['EngineConfig.onnxruntime.use_cuda']:
                import torch  # Loads the matching CUDA/cuDNN runtime when opted in.
                torch.set_num_threads(4)
            self.engine = RapidOCR(params=PARAMS)
        return self.engine

    def get_recognition_engine(self):
        if self.recognition_engine is None:
            from rapidocr import RapidOCR
            # Current CUDA/cuDNN shape changes show 0.2--0.9 s recognition tails.
            # The same unchanged small model on four CPU threads is 11--31 ms
            # for this small title batch; see the bounded runtime probes.
            self.recognition_engine = RapidOCR(params=RECOGNITION_PARAMS)
        return self.recognition_engine

    def __call__(self, source, main_only=False):
        started = time.perf_counter()
        if isinstance(source, np.ndarray):
            im = source
            source_name = 'in_memory_synthetic'
        else:
            im = cv2.imread(str(source))
            source_name = str(source)
            if im is None:
                raise ValueError(f'Cannot decode {source}')
        t = time.perf_counter()
        timing = dict(decode=t-started)
        matches = self.matcher(im)
        timing['sprite'] = time.perf_counter()-t
        t = time.perf_counter()
        layout = locate_layout(im, matches, self.profile)
        timing['layout'] = time.perf_counter()-t
        output = dict(source=source_name, dimensions=[im.shape[1], im.shape[0]],
                      all_matches=matches, layout=layout, page_accepted=layout['accepted'],
                      selected_main_tab=layout['selected_main_tab'],
                      selected_main_label=layout['selected_main_label'],
                      sub_tabs=[], selected_sub_tab=None, engine_ui_tree=False,
                      ocr=dict(executed=False, cache_hit=False, detected_regions=0,
                               recognized_regions=0, area_fraction=0, text_regions=[]))
        roi_bounds = layout['subtab_roi']
        if not layout['accepted'] or roi_bounds is None or main_only:
            output['ocr']['skip_reason'] = ('main_only_requested' if main_only else
                layout.get('ocr_skip_reason', layout['reason']))
            # Never carry stale text across rejected page states.
            if not layout['accepted']:
                self.cache = None
        else:
            l, top, r, bottom = roi_bounds
            crop = np.ascontiguousarray(im[top:bottom, l:r])
            key = (layout['selected_main_tab'], tuple(roi_bounds),
                   hashlib.sha256(crop.tobytes()).hexdigest()) if self.reuse_ocr else None
            t = time.perf_counter()
            if self.reuse_ocr and self.cache is not None and key == self.cache[0]:
                evidence = copy.deepcopy(self.cache[1])
                evidence.update(executed=False, cache_hit=True)
            else:
                engine = self.get_engine()
                recognition_engine = self.get_recognition_engine()
                timing['ocr_runtime_prepare'] = time.perf_counter()-t
                t = time.perf_counter()
                # Detect only inside the anchored ROI, not the whole screenshot.
                det = engine(crop, use_det=True, use_cls=False, use_rec=False)
                timing['text_detection'] = time.perf_counter()-t
                t = time.perf_counter()
                kept, rejected, crops = [], [], []
                boxes = [] if det.boxes is None else det.boxes
                s = layout['scale']
                dx, dy = layout['offset']
                for raw_box in boxes:
                    poly = np.asarray(raw_box, dtype=float) + [l, top]
                    x0, y0 = poly.min(axis=0)
                    x1, y1 = poly.max(axis=0)
                    # Calibrated font scale/alignment rejects small subtitles/progress
                    # BEFORE recognition; clipped edge lines remain unknown.
                    reason = None
                    ref_x = (x0-dx)/s
                    ref_h = (y1-y0)/s
                    if not self.profile['title_left_reference_range'][0] <= ref_x <= self.profile['title_left_reference_range'][1]:
                        reason = 'not_title_alignment'
                    elif not self.profile['title_height_reference_range'][0] <= ref_h <= self.profile['title_height_reference_range'][1]:
                        reason = 'not_title_font_size'
                    elif y0 < top+3*s or y1 > bottom-3*s:
                        reason = 'clipped_at_roi_edge'
                    entry = dict(polygon=poly.tolist(), bounds=[float(x0), float(y0), float(x1), float(y1)])
                    if reason:
                        entry['reason'] = reason
                        rejected.append(entry)
                    else:
                        kept.append(entry)
                        crops.extend(engine.crop_text_regions(crop, np.asarray([raw_box])))
                timing['filter_and_crop'] = time.perf_counter()-t
                t = time.perf_counter()
                if crops:
                    rec = recognition_engine.recognize_txt(crops)  # Only title lines.
                    for entry, text, score in zip(kept, rec.txts, rec.scores):
                        entry.update(text=text, score=float(score))
                timing['text_recognition'] = time.perf_counter()-t
                tensor = engine.text_det.preprocess_op.resize(crop)
                evidence = dict(executed=True, cache_hit=False, detected_regions=len(boxes),
                                recognized_regions=len(kept), text_regions=kept,
                                rejected_before_recognition=rejected,
                                detector_tensor_wh=[tensor.shape[1], tensor.shape[0]])
                if self.reuse_ocr:
                    self.cache = (key, copy.deepcopy(evidence))
            evidence.update(roi_bounds=roi_bounds,
                            area_fraction=crop.shape[0]*crop.shape[1]/(im.shape[0]*im.shape[1]),
                            raw_text_corrected=False)
            output['ocr'] = evidence
            t = time.perf_counter()
            output['sub_tabs'], output['selected_sub_tab'] = make_tabs(im, evidence['text_regions'], layout)
            timing['subtab_structure'] = time.perf_counter()-t
        timing['total'] = time.perf_counter()-started
        output['timing_seconds'] = timing
        output['sub_selection_status'] = 'visible' if output['selected_sub_tab'] else 'unknown_or_not_applicable'
        return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--main-only', action='store_true')
    parser.add_argument('--cache', action='store_true')
    args = parser.parse_args()
    recognizer = GuideRecognizer(reuse_ocr=args.cache)
    for path in args.images:
        output = recognizer(path, main_only=args.main_only)
        (HERE/(path.stem+'-roi-result.json')).write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
        print(path.name, output['selected_main_label'], output['selected_sub_tab'],
              [x['raw_text'] for x in output['sub_tabs']], output['timing_seconds'], flush=True)
