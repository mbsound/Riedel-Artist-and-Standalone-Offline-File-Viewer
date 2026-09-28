// Ghidra GhidraScript (Java). Decompiles every serializer/packer function and writes C.
// Output path from env DECOMP_OUT (fallback next to script).
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.util.task.ConsoleTaskMonitor;
import java.io.*;
import java.util.*;

public class DecompileTargets extends GhidraScript {
    static final String[] INCLUDE = {
        "RTXSerializer", "::pack", "JsonSerializer",
        "convertBPKey", "BPConfig", "AudioPort", "AudioChannel", "AudioFilter",
        "Profile", "Partyline", "Antenna", "Trigger", "Gpio", "GPIO",
        "NetSettings", "NetConfig", "packForSaving", "unpack"
    };
    static final String[] EXCLUDE = { "~", "std::", "rapidjson", "_M_", "__cxx", "allocator" };

    public void run() throws Exception {
        String out = System.getenv("DECOMP_OUT");
        if (out == null) out = "decomp_out.c";
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        ConsoleTaskMonitor mon = new ConsoleTaskMonitor();
        FunctionManager fm = currentProgram.getFunctionManager();
        LinkedHashMap<String,Function> chosen = new LinkedHashMap<>();
        for (Function f : fm.getFunctions(true)) {
            String full = f.getName(true);
            boolean inc = false;
            for (String s : INCLUDE) if (full.contains(s)) { inc = true; break; }
            if (!inc) continue;
            boolean ex = false;
            for (String s : EXCLUDE) if (full.contains(s)) { ex = true; break; }
            if (ex) continue;
            chosen.put(f.getEntryPoint().toString(), f);
        }
        PrintWriter w = new PrintWriter(new FileWriter(out));
        w.println("// Decompiled " + chosen.size() + " functions from " + currentProgram.getName());
        int ok = 0;
        for (Function f : chosen.values()) {
            w.println("// ==== " + f.getName(true) + "  @ " + f.getEntryPoint() + " ====");
            try {
                DecompileResults r = di.decompileFunction(f, 60, mon);
                if (r != null && r.decompileCompleted()) { w.print(r.getDecompiledFunction().getC()); ok++; }
                else w.println("// decompile failed: " + (r!=null?r.getErrorMessage():"no result"));
            } catch (Exception e) { w.println("// exception: " + e); }
            w.println();
        }
        w.close();
        println("WROTE " + ok + "/" + chosen.size() + " functions to " + out);
    }
}
