import math
def loop_frame(output_frame,output_start,output_fps,source_fps,action_start,action_end):
 values=[output_frame,output_start,output_fps,source_fps,action_start,action_end]
 if any(not math.isfinite(x) for x in values) or output_fps<=0 or source_fps<=0 or action_end<=action_start:raise ValueError('Nonempty finite Action clock required')
 return action_start+(((output_frame-output_start)*source_fps/output_fps)%(action_end-action_start))
