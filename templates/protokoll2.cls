% protokoll.cls -- version 0.1 -- last changed: see mtime of the file ;)
%
%
% Author: Sebastian Günther <samson@asta.rwth-aachen.de>

% zuerst mal LaTeX's formalzeug
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{protokoll2}[2004/06/04 protokoll.cls v0.1 macht Protokolle (VV)]
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
%\ExecuteOptions{draft}
\ProcessOptions\relax

% die restlichen optionen geben wir an article weiter
\LoadClass[a4paper]{article}

% so ein paar sachen die wir eh immer brauchen
\RequirePackage[ngerman]{babel}
\RequirePackage[\VAR{latex_geometry}]{geometry}
%\RequirePackage{lineno}
\RequirePackage{longtable}
\RequirePackage{framed}
\RequirePackage{eurosym}
\RequirePackage[babel]{csquotes}
\RequirePackage{polyglossia}
\RequirePackage{enumitem}
\RequirePackage{color}
\RequirePackage{xcolor}
\RequirePackage[breakable]{tcolorbox}
\RequirePackage{linegoal}
\RequirePackage[hyphens]{url}
\ENV{for package in additional_packages}
    \RequirePackage\VAR{package}
\ENV{endfor}

\setlistdepth{\VAR{maxdepth}}
\renewlist{itemize}{itemize}{\VAR{maxdepth}}
\ENV{for index in range(maxdepth)}
    \setlist[itemize,\VAR{index+1}]{label=\VAR{loop.cycle(*bulletpoints)}}
\ENV{endfor}

\definecolor{itemizebackground}{gray}{0.95}

\setmainlanguage[babelshorthands=true]{german}

\ENV{macro specify_font(font, name)}
    \set\VAR{name}font[
    \ENV{if font.path is defined}
        Path=\VAR{font.path},
    \ENV{endif}
    \ENV{if font.extension is defined}
        Extension=\VAR{font.extension},
    \ENV{endif}
        BoldFont={\VAR{font.bold}},
        ItalicFont={\VAR{font.italic}},
        BoldItalicFont={\VAR{font.bolditalic}}
    ]{\VAR{font.regular}}
\ENV{endmacro}

\RequirePackage{fontspec}
\VAR{specify_font(fonts.roman, "roman")}
\VAR{specify_font(fonts.sans, "sans")}
\VAR{specify_font(fonts.mono, "mono")}
\VAR{specify_font(fonts.main, "main")}
%\setromanfont[
%    BoldFont={\VAR{fonts.roman.bold}},
%    ItalicFont={\VAR{fonts.roman.italic}},
%    BoldItalicFont={\VAR{fonts.roman.bolditalic}}
%]{\VAR{fonts.roman.regular}}
%\setsansfont[
%    BoldFont={\VAR{fonts.sans.bold}},
%    ItalicFont={\VAR{fonts.sans.italic}},
%    BoldItalicFont={\VAR{fonts.sans.bolditalic}}
%]{\VAR{fonts.sans.regular}}
%\setmonofont[
%    BoldFont={\VAR{fonts.mono.bold}},
%    ItalicFont={\VAR{fonts.mono.italic}},
%    BoldItalicFont={\VAR{fonts.mono.bolditalic}}
%]{\VAR{fonts.mono.regular}}
%\setmainfont[
%\ENV{if fonts.main.path is defined}
%    Path=\VAR{fonts.main.path},
%\ENV{endif}
%\ENV{if fonts.main.extension is defined}
%    Extension=\VAR{fonts.main.extension},
%\ENV{endif}
%    BoldFont={\VAR{fonts.main.bold}},
%    ItalicFont={\VAR{fonts.main.italic}},
%    BoldItalicFont={\VAR{fonts.main.bolditalic}}
%]{\VAR{fonts.main.regular}}


% nicht einrücken und benutzerinnendefinierte kopfzeile
\setlength{\parindent}{0cm}
\setlength{\parskip}{1ex}
\pagestyle{\VAR{latex_pagestyle|default("myheadings")}}

\ENV{if latex_header_footer}
    \renewcommand{\headrulewidth}{0pt}
    \renewcommand{\footrulewidth}{0.5pt}
    \def\footerprotocoltext{\relax}
    \rfoot[]{\rmfamily\small\footerprotocoltext~~|~~\textbf{\thepage}}
    \lfoot[\rmfamily\small\textbf{\thepage}~~|~~\footerprotocoltext]{}
    \cfoot{}
    \chead{}
    \lhead[]{}
    \rhead[]{}
\ENV{endif}

%\renewcommand*{\rmdefault}{phv}
%\renewcommand*{\sfdefault}{phv}

% Titel
\newcommand{\Kopf}[1]{\markboth{#1}{#1}}
\newcommand{\Titel}[2]{
  \def\footerprotocoltext{#2}
  %\markboth{#2}{#2}
  %\markright{#2}
  %\thispagestyle{plain}
  \begin{center}
    \textbf{#1}
  \end{center}
}

% Tops
\renewcommand{\thesection}{TOP~\arabic{section}}
\renewcommand{\thesubsection}{TOP~\arabic{section}~(\alph{subsection})}
\newcommand{\TOP}[1]{\section{#1}}
\newcommand{\unterTOP}[1]{\subsection{#1}}
% Fürs Inhaltsverzeichnisanpassen
\renewcommand{\l@section}{\@dottedtocline{1}{1.5em}{4em}}
\renewcommand{\l@subsection}{\@dottedtocline{2}{5.5em}{5.2em}}
\renewcommand{\contentsname}{Tagesordnung}
\newcommand{\Inhalt}{\tableofcontents}

% Zeilen-Numerierungen
\newcommand{\ZeilenNummerierung}{\pagewiselinenumbers\linenumbers}
\newcommand{\EndeZeilenNummerierung}{\nolinenumbers}

% Anwesenheit
\newenvironment{Anw}{\begin{list}{}{%
      \renewcommand{\makelabel}[1]{\hfill ##1 }%
      \settowidth{\labelwidth}{Anwesenheit:~}%
      \addtolength{\labelwidth}{\labelsep}%
      \setlength{\leftmargin}{\labelwidth}%
      \addtolength{\leftmargin}{\labelsep}%
      \addtolength{\leftmargin}{\labelsep}%
      \setlength{\itemsep}{0pt}%
      \setlength{\parsep}{0pt}%
      \setlength{\topsep}{0pt}%
    }%
}%
{\end{list}}

% Abwesenheit
\newenvironment{Abw}{\begin{list}{}{%
      \renewcommand{\makelabel}[1]{\hfill ##1 }%
      \settowidth{\labelwidth}{Anwesenheit:~}%
      \addtolength{\labelwidth}{\labelsep}%
      \setlength{\leftmargin}{\labelwidth}%
      \addtolength{\leftmargin}{\labelsep}%
      \addtolength{\leftmargin}{\labelsep}%
      \setlength{\itemsep}{0pt}%
      \setlength{\parsep}{0pt}%
      \setlength{\topsep}{0pt}%
    }%
}%
{\end{list}}

% Abkürzungen
\newenvironment{Abk}{%
  \begin{list}{}{%
	Abkürzungen:
      \renewcommand{\makelabel}[1]{\hfill ##1 }%
      \setlength{\labelwidth}{2cm}%
      \addtolength{\labelwidth}{\labelsep}%
      \setlength{\leftmargin}{\labelwidth}%
      \addtolength{\leftmargin}{\labelsep}%
      \addtolength{\leftmargin}{\labelsep}%
      \setlength{\itemsep}{0pt}%
      \setlength{\parsep}{0pt}%
      \setlength{\topsep}{0pt}%
    }%
}%
{\end{list}}

% Unterschriften für eine und zwei Personen
\newcommand{\Unterschrift}[2]{
  \vspace*{1.4cm}
  \begin{center}
    \rule{.4\linewidth}{.15mm} \\
    #1 \\
    \footnotesize{(#2)}
  \end{center}
}
\newcommand{\ZweiUnterschrift}[4]{
  \vspace*{1.4cm}
  \begin{center}
    \parbox[t]{.4\linewidth}{
      \rule{\linewidth}{.15mm} \\
      \vspace*{-.4cm}\begin{center}
        #1 \\
	\footnotesize{(#2)}
      \end{center}
    }
    \hspace*{.1\linewidth}
    \parbox[t]{.4\linewidth}{
      \rule{\linewidth}{.15mm} \\
      \vspace*{-.4cm}\begin{center}
	#3 \\
	\footnotesize{(#4)}
      \end{center}
    }
  \end{center}
}

% \newcommand{\Antrag}[1]{
% %  \setlength{\arrayrulewidth}{2mm}
% %  \begin{longtable}{|ll}
% %    \hspace{2mm} & \parbox[t]{17cm}{#1}
% %  \end{longtable}
%   \begingroup
%   \rule{2mm}{2mm}
%   \leftskip10cm
% %  \rightskip\leftskip
%   #1
%   \par
%   \endgroup
% }

\newcommand{\Antrag}[1]{
  \setlength{\arrayrulewidth}{2mm}
  \begin{longtable}{|ll}
   % \hspace{2mm} & \parbox[t]{17cm}{#1}
    \hspace{2mm} & \begin{minipage}{17cm} #1\end{minipage}
  \end{longtable}
}

\newenvironment{antrag}
{%
  \par%
  \begingroup%
  \leftskip1cm%
}
{\par\endgroup}


\newcommand{\Bericht}[1]{
  \Antrag{#1}
}

\newcommand{\PE}[2]{\textbf{Persönliche Erklärung von #1:}\\\emph{\glqq{}#2\grqq{}}\\}

% Styling der Todo und Beschlusstags im Protokoll
\newcommand{\Todo}[4]{\textbf{{#1}}: #2: #3 -- #4}
\newcommand{\Beschluss}[2][]{\textbf{Beschluss:} #2 \def\temp{#1}\ifx\temp\empty\else\textit{(#1)}\fi}
