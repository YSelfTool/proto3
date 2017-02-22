% protokoll.cls -- version 0.1 -- last changed: see mtime of the file ;)
%
%
% Author: Sebastian G�nther <samson@asta.rwth-aachen.de>

% zuerst mal LaTeX's formalzeug
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{protokoll2}[2004/06/04 protokoll.cls v0.1 macht Protokolle (VV)]
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
%\ExecuteOptions{draft}
\ProcessOptions\relax

% die restlichen optionen geben wir an article weiter
\LoadClass[a4paper]{article}

% so ein paar sachen die wir eh immer brauchen
\RequirePackage{ngerman}
\RequirePackage[T1]{fontenc}
\RequirePackage[utf8]{inputenc}
\RequirePackage[vmargin=1.5cm,hmargin={1.5cm,1.2cm},bindingoffset=8mm]{geometry}
%\RequirePackage{lineno}
\RequirePackage{longtable}
\RequirePackage{framed}
\RequirePackage{eurosym}
\RequirePackage{csquotes}


% nicht einr�cken und benutzerinnendefinierte kopfzeile
\setlength{\parindent}{0cm}
\setlength{\parskip}{1ex}
\pagestyle{myheadings}

\renewcommand*{\rmdefault}{phv}
\renewcommand*{\sfdefault}{phv}

% Titel
\newcommand{\Kopf}[1]{\markboth{#1}{#1}}
\newcommand{\Titel}[2]{
  \markboth{#2}{#2}
  \markright{#2}
  \thispagestyle{plain}
  \begin{center}
    \textbf{#1}
  \end{center}
}

% Tops
\renewcommand{\thesection}{TOP~\arabic{section}}
\renewcommand{\thesubsection}{TOP~\arabic{section}~(\alph{subsection})}
\newcommand{\TOP}[1]{\section{#1}}
\newcommand{\unterTOP}[1]{\subsection{#1}}
% F�rs Inhaltsverzeichnisanpassen
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

% Abk�rzungen
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

% Unterschriften f�r eine und zwei Personen
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

