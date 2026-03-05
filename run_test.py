import llm
import sys
# make sure llm_consortium is registered? 
# Usually llm CLI loads plugins via setuptools entrypoints.
# Let's try to just use llm programmatically
try:
    model = llm.get_model('test-cns')
    print("Found model:", model)
    response = model.prompt('Test question')
    print("Executing prompt...")
    for chunk in response:
        print("Chunk:", repr(chunk))
except Exception as e:
    import traceback
    traceback.print_exc()
