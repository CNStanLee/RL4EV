function make_waveform_figs(cases)
% MAKE_WAVEFORM_FIGS  Per-case waveform comparison of the six PFC strategies
% before / during / after a sensor-chain injection (from results/emi/ts).
%   make_waveform_figs()                 all cases in tests.csv
%   make_waveform_figs({'E-DC-01c'})     subset
% Output: docs/figures/waveforms/
%   <case>_state.png       six strategies overlaid: real vs internal Vdc, Iref,
%                          per-cycle Iac RMS, per-cycle THD50, P_charge, trips
%   <case>_iac.png         per strategy: 2 cycles of real Iac before / during /
%                          after the bias
%   <case>_transition.png  per strategy: Iac and Vdc around injection onset and
%                          removal (where the removal spikes / trips occur)
mdir = fileparts(mfilename('fullpath'));
rdir = fullfile(mdir, 'results', 'emi'); tdir = fullfile(rdir, 'ts');
fdir = fullfile(mdir, 'docs', 'figures', 'waveforms'); if ~exist(fdir, 'dir'), mkdir(fdir); end
T = readtable(fullfile(mdir, 'tests.csv'), 'TextType', 'string');
if nargin < 1 || isempty(cases), cases = cellstr(T.test_id'); end
if ischar(cases), cases = {cases}; end
sc = readtable(fullfile(rdir, 'scorecard.csv'), 'TextType', 'string');
V = {'CRPR', 'MPCC_P', 'MPCC_D', 'MPCC_D_F1', 'MPCC_D_F10', 'MPCC_D_R'};
col = [0.15 0.15 0.15; 0.85 0.33 0.10; 0.00 0.45 0.74; 0.47 0.67 0.19; 0.49 0.18 0.56; 0.93 0.69 0.13];
set(0, 'DefaultAxesFontSize', 8, 'DefaultLineLineWidth', 0.9);
tripname = {'UV', 'OV', 'OC', 'BOV', 'BOC'};

for c = 1:numel(cases)
    id = cases{c}; row = T(T.test_id == id, :);
    t_on = row.t_on; t_off = row.t_on + row.dwell;
    lab = sprintf('%s: %s %s %+g', id, row.channel, row.shape, row.amp);
    if ~ismissing(row.channel2) && strlength(row.channel2) > 0, lab = sprintf('%s, %s %+g', lab, row.channel2, row.amp2); end
    D = struct('X', {}, 'ti', {}, 'ia', {}, 'tc', {}, 'irms', {}, 'thd', {}, 'trip', {}, 'ttrip', {});
    for i = 1:6
        p = fullfile(tdir, sprintf('%s_%s.csv', id, V{i})); q = fullfile(tdir, sprintf('%s_%s_iac.mat', id, V{i}));
        if ~exist(p, 'file') || ~exist(q, 'file'), D(i).X = []; continue; end
        D(i).X = readtable(p); M = load(q); D(i).ti = M.t_iac; D(i).ia = double(M.Iac);
        [D(i).tc, D(i).irms, D(i).thd] = per_cycle(D(i).ti, D(i).ia);
        r = sc(sc.test_id == id & sc.VARIANT_NAME == V{i}, :);
        D(i).trip = 0; D(i).ttrip = NaN;
        if ~isempty(r) && ismember('trip', r.Properties.VariableNames), D(i).trip = r.trip(1); D(i).ttrip = t_on + r.t_trip_ms(1) / 1e3; end
    end
    if all(arrayfun(@(d) isempty(d.X), D)), fprintf('[wave] %s: no data\n', id); continue; end
    fig_state(id, lab, D, t_on, t_off);
    fig_iac(id, lab, D, t_on, t_off);
    fig_transition(id, lab, D, t_on, t_off);
    fprintf('[wave] %s\n', id);
end

% ------------------------------------------------------------------------
    function fig_state(id, lab, D, t_on, t_off)
        f = figure('Visible', 'off', 'Color', 'w', 'Position', [50 50 1000 900]);
        tl = tiledlayout(f, 5, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
        ax = gobjects(5, 1); for k = 1:5, ax(k) = nexttile(tl); hold(ax(k), 'on'); end
        for i = 1:6
            X = D(i).X; if isempty(X), continue; end
            plot(ax(1), X.t, X.Vdc_real, 'Color', col(i, :), 'DisplayName', V{i});
            plot(ax(2), X.t, X.Iref, 'Color', col(i, :));
            plot(ax(3), D(i).tc, D(i).irms, '.-', 'Color', col(i, :));
            plot(ax(4), D(i).tc, D(i).thd, '.-', 'Color', col(i, :));
            plot(ax(5), X.t, X.P_charge / 1e3, 'Color', col(i, :));
            if D(i).trip > 0 && ~isnan(D(i).ttrip)
                xline(ax(1), D(i).ttrip, '-', sprintf('%s %s', V{i}, tripname{D(i).trip}), 'Color', col(i, :), ...
                    'LabelOrientation', 'aligned', 'FontSize', 7, 'HandleVisibility', 'off', 'Interpreter', 'none');
            end
        end
        % internal Vdc of the first available strategy (identical for all in the Vdc-chain cases)
        i0 = find(~arrayfun(@(d) isempty(d.X), D), 1);
        plot(ax(1), D(i0).X.t, D(i0).X.Vdc_int, '--', 'Color', [0.45 0.45 0.45], 'DisplayName', 'internal Vdc');
        yline(ax(1), 450, ':r', 'HandleVisibility', 'off'); yline(ax(1), 300, ':r', 'HandleVisibility', 'off');
        ylabel(ax(1), 'V_{dc} real / internal (V)'); ylabel(ax(2), 'I_{ref} (A)'); ylabel(ax(3), 'I_{ac} RMS per cycle (A)');
        ylabel(ax(4), 'THD50 per cycle (%)'); ylabel(ax(5), 'P_{charge} (kW)'); xlabel(ax(5), 't (s)');
        set(ax(4), 'YScale', 'log');
        for k = 1:5, shade(ax(k), t_on, t_off); xlim(ax(k), [0.65 1.3]); grid(ax(k), 'on'); end
        legend(ax(1), 'Location', 'eastoutside', 'Interpreter', 'none');
        title(tl, [lab '  |  shaded = injection on'], 'Interpreter', 'none');
        save_(f, fullfile(fdir, [id '_state']));
    end

    function fig_iac(id, lab, D, t_on, t_off)
        f = figure('Visible', 'off', 'Color', 'w', 'Position', [50 50 1100 620]);
        tl = tiledlayout(f, 2, 3, 'TileSpacing', 'compact', 'Padding', 'compact');
        w = [t_on - 0.04, t_on; t_off - 0.04, t_off; t_off + 0.26, t_off + 0.30];   % before / during / after, 2 cycles each
        cw = [0.55 0.55 0.55; 0.85 0.20 0.10; 0.00 0.45 0.74]; nm = {'before', 'during (last 2 cycles)', 'after (last 2 cycles)'};
        for i = 1:6
            ax = nexttile(tl); hold(ax, 'on');
            if isempty(D(i).X), title(ax, [V{i} ' (no data)'], 'Interpreter', 'none'); continue; end
            for k = 1:3
                m = D(i).ti >= w(k, 1) & D(i).ti < w(k, 2);
                plot(ax, (D(i).ti(m) - w(k, 1)) * 1e3, D(i).ia(m), 'Color', cw(k, :), 'DisplayName', nm{k});
            end
            r = sc(sc.test_id == id & sc.VARIANT_NAME == V{i}, :);
            vn = strrep(V{i}, '_', '\_'); ttl = vn;
            if ~isempty(r), ttl = sprintf('%s   THD50 %.1f -> %.1f -> %.1f %%   I_{dc} %+.1f A', vn, r.THD50_pre_pct, r.THD50_dur_pct, r.THD50_post_pct, r.I_dc_A); end
            title(ax, ttl, 'Interpreter', 'tex', 'FontSize', 8); grid(ax, 'on'); xlim(ax, [0 40]);
            if i > 3, xlabel(ax, 'ms'); end, if any(i == [1 4]), ylabel(ax, 'I_{ac} real (A)'); end
            if i == 1, legend(ax, 'Location', 'southwest', 'FontSize', 7); end
        end
        title(tl, [lab '  |  real grid current before / during / after the bias'], 'Interpreter', 'none');
        save_(f, fullfile(fdir, [id '_iac']));
    end

    function fig_transition(id, lab, D, t_on, t_off)
        f = figure('Visible', 'off', 'Color', 'w', 'Position', [50 50 1100 760]);
        tl = tiledlayout(f, 4, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
        ev = [t_on, t_off]; evn = {'injection onset', 'injection removal'};
        for e = 1:2
            axI = nexttile(tl, e); hold(axI, 'on'); axV = nexttile(tl, e + 2); hold(axV, 'on');
            axR = nexttile(tl, e + 4); hold(axR, 'on'); axP = nexttile(tl, e + 6); hold(axP, 'on');
            for i = 1:6
                if isempty(D(i).X), continue; end
                m = D(i).ti >= ev(e) - 0.02 & D(i).ti <= ev(e) + 0.06;
                plot(axI, (D(i).ti(m) - ev(e)) * 1e3, D(i).ia(m), 'Color', col(i, :), 'DisplayName', V{i});
                X = D(i).X; mm = X.t >= ev(e) - 0.02 & X.t <= ev(e) + 0.06;
                plot(axV, (X.t(mm) - ev(e)) * 1e3, X.Vdc_real(mm), 'Color', col(i, :));
                plot(axR, (X.t(mm) - ev(e)) * 1e3, X.Iref(mm), 'Color', col(i, :));
                plot(axP, (X.t(mm) - ev(e)) * 1e3, X.P_charge(mm) / 1e3, 'Color', col(i, :));
                if D(i).trip > 0 && ~isnan(D(i).ttrip) && abs(D(i).ttrip - ev(e)) <= 0.06
                    xline(axI, (D(i).ttrip - ev(e)) * 1e3, '-', [V{i} ' ' tripname{D(i).trip}], 'Color', col(i, :), 'FontSize', 7, 'HandleVisibility', 'off', 'Interpreter', 'none');
                end
            end
            yline(axI, 65, ':r', 'OC 65 A', 'HandleVisibility', 'off'); yline(axI, -65, ':r', 'HandleVisibility', 'off');
            for a = [axI axV axR axP], xline(a, 0, 'k:', 'HandleVisibility', 'off'); xlim(a, [-20 60]); grid(a, 'on'); end
            title(axI, evn{e}); ylabel(axI, 'I_{ac} real (A)'); ylabel(axV, 'V_{dc} real (V)'); ylabel(axR, 'I_{ref} (A)'); ylabel(axP, 'P_{charge} (kW)');
            xlabel(axP, 'ms from event');
            if e == 1, legend(axI, 'Location', 'southwest', 'NumColumns', 3, 'FontSize', 7, 'Interpreter', 'none'); end
        end
        title(tl, [lab '  |  transitions (OC threshold dotted)'], 'Interpreter', 'none');
        save_(f, fullfile(fdir, [id '_transition']));
    end

% ------------------------------------------------------------------------
    function [tc, irms, thd] = per_cycle(t, x)
        t0 = t(1); n = floor((t(end) - t0) * 50); tc = zeros(n, 1); irms = zeros(n, 1); thd = zeros(n, 1);
        for k = 1:n
            a = t0 + (k - 1) / 50; m = t >= a & t < a + 1 / 50; xs = x(m);
            tc(k) = a + 0.01; irms(k) = sqrt(mean(xs.^2));
            xs = xs - mean(xs); N = numel(xs); X = abs(fft(xs)) / N; X = X(1:floor(N / 2));
            df = 1 / (N * median(diff(t(m)))); k1 = round(50 / df); A1 = X(k1 + 1); h = 0;
            for hh = 2:50, kk = round(hh * 50 / df); if kk + 1 <= numel(X), h = h + X(kk + 1)^2; end, end
            thd(k) = 100 * sqrt(h) / max(A1, 1e-6);
        end
    end
    function shade(ax, a, b)
        yl = ylim(ax); patch(ax, [a b b a], [yl(1) yl(1) yl(2) yl(2)], [1 0.92 0.75], 'EdgeColor', 'none', 'FaceAlpha', 0.5, 'HandleVisibility', 'off');
        uistack(findobj(ax, 'Type', 'patch'), 'bottom');
    end
    function save_(f, base)
        print(f, [base '.png'], '-dpng', '-r130'); close(f);
    end
end
