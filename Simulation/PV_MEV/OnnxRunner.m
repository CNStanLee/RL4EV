classdef OnnxRunner < matlab.System
    % OnnxRunner  Run an ONNX model in Simulink through Python onnxruntime.
    %
    % Interpreted-execution MATLAB System block (no code generation).  One
    % input row vector (1 x NumIn, single) -> one output row vector
    % (1 x NumOut, single) = concatenation of all model outputs in order.
    % Needs pyenv pointing at an environment with onnxruntime (conda env
    % hgq2).  Used for the HGQ2 harmonic estimator (80 -> 8) and the EMI
    % detector (92 -> 16).  Exact by construction with respect to the ONNX
    % file; replace with a fixed-point implementation for HDL.
    properties (Nontunable)
        ModelFile = ''      % path to .onnx
        NumIn  = 80         % input vector length
        NumOut = 8          % total output length (all outputs concatenated)
        SampleTime = -1     % block sample time (s); -1 inherited
    end
    properties (Access = private)
        h = 0          % session handle in onnx_bridge.py
    end
    methods
        function obj = OnnxRunner(varargin)
            setProperties(obj, nargin, varargin{:});
        end
    end
    methods (Access = protected)
        function setupImpl(obj)
            here = fileparts(mfilename('fullpath'));
            sys = py.importlib.import_module('sys');
            if ~any(strcmp(cellfun(@char, cell(sys.path), 'UniformOutput', false), here)), sys.path.insert(int32(0), here); end
            br = py.importlib.import_module('onnx_bridge');   % no reload: several blocks share the session table
            % the block dialog may hand over the literal text including quotes
            mf = strtrim(char(string(obj.ModelFile))); mf = mf(mf ~= '''' & mf ~= '"');
            if ~isfile(mf), error('OnnxRunner: model file not found: %s', mf); end
            obj.h = double(br.load(mf, int32(1)));
        end
        function y = stepImpl(obj, u)
            br = py.importlib.import_module('onnx_bridge');
            r = br.run(int32(obj.h), py.list(double(u(:)')), int32(obj.NumIn));
            y = single(cellfun(@double, cell(r)));
            y = y(1:obj.NumOut);
        end
        function releaseImpl(obj)
            try, br = py.importlib.import_module('onnx_bridge'); br.close(int32(obj.h)); catch, end
        end
        function resetImpl(~)
        end
        function y = getOutputSizeImpl(obj), y = [1 obj.NumOut]; end
        function y = getOutputDataTypeImpl(~), y = 'single'; end
        function y = isOutputComplexImpl(~), y = false; end
        function y = isOutputFixedSizeImpl(~), y = true; end
        function sts = getSampleTimeImpl(obj)
            if obj.SampleTime > 0
                sts = createSampleTime(obj, 'Type', 'Discrete', 'SampleTime', obj.SampleTime);
            else
                sts = createSampleTime(obj, 'Type', 'Inherited');
            end
        end
        function flag = isInputDirectFeedthroughImpl(~, ~), flag = true; end
    end
    methods (Static, Access = protected)
        function simMode = getSimulateUsingImpl(), simMode = 'Interpreted execution'; end
        function flag = showSimulateUsingImpl(), flag = false; end
    end
end
